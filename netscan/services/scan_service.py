import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from sqlmodel import Session, select
from netscan.db import engine
from netscan.models import (
    IPAddress,
    IPHistory,
    IPStatus,
    ScanJob,
    ScanStatus,
    Subnet,
)
from netscan.scanner.cidr import expand_cidr_hosts
from netscan.scanner.classifier import StateClassifier
from netscan.scanner.runner import NmapScanner
from netscan.services.webhook_service import WebhookDispatcher

_webhook_tasks: set = set()
_scan_tasks: set = set()


def _track_webhook_task(task: asyncio.Task) -> None:
    _webhook_tasks.discard(task)
    if task.exception():
        logger.error("Webhook task failed: %s", task.exception())


def _track_scan_task(task: asyncio.Task) -> None:
    _scan_tasks.discard(task)
    if task.exception():
        logger.error("Scan task failed: %s", task.exception())


logger = logging.getLogger(__name__)


def recover_stale_scan_jobs(session: Session, max_age_seconds: int = 600) -> int:
    """Mark QUEUED/RUNNING scan jobs older than max_age_seconds as FAILED.

    Returns the number of jobs recovered.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stale = session.exec(
        select(ScanJob).where(
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
            ScanJob.created_at < cutoff,
        )
    ).all()
    count = 0
    for job in stale:
        job.status = ScanStatus.FAILED
        job.error_message = "Recovered by startup: job stuck"
        job.completed_at = datetime.now(timezone.utc)
        session.add(job)
        count += 1
    if count:
        session.commit()
        logger.warning("Recovered %d stale scan job(s)", count)
    return count


def check_active_scan(session: Session, subnet_id: uuid.UUID) -> ScanJob | None:
    """Return the active ScanJob for a subnet, or None if no scan is in progress.

    Note: This has a TOCTOU race window (check-then-insert is not atomic).
    Under the single-instance constraint documented in PRODUCTION_READINESS.md,
    this is acceptable. A unique partial index on (subnet_id, status) would be
    the proper fix for multi-instance deployments, but requires PostgreSQL.
    """
    return session.exec(
        select(ScanJob).where(
            ScanJob.subnet_id == subnet_id,
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
        )
    ).first()


class ScanService:
    """Executes network scans, evaluates state transitions, and records audit history."""

    def __init__(self):
        self.scanner = NmapScanner()

    async def execute_scan(self, scan_job_id: uuid.UUID) -> None:
        """Background worker method to execute a scan job."""
        task = asyncio.current_task()
        if task is not None:
            _scan_tasks.add(task)
            task.add_done_callback(_track_scan_task)
        scan_start = time.monotonic()
        with Session(engine) as session:
            job = session.get(ScanJob, scan_job_id)
            if not job:
                logger.error("ScanJob %s not found.", scan_job_id)
                return

            subnet = session.get(Subnet, job.subnet_id)
            if not subnet:
                job.status = ScanStatus.FAILED
                job.error_message = f"Subnet {job.subnet_id} not found."
                session.add(job)
                session.commit()
                logger.error("ScanJob %s failed: subnet %s not found.", scan_job_id, job.subnet_id)
                return

            active = check_active_scan(session, job.subnet_id)
            if active and active.id != job.id:
                job.status = ScanStatus.FAILED
                job.error_message = f"Skipped: active scan exists on subnet (job {active.id})"
                job.completed_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()
                logger.info("ScanJob %s skipped: active scan %s on subnet", scan_job_id, active.id)
                return

            job.status = ScanStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            subnet_cidr = subnet.cidr
            job_subnet_id = job.subnet_id

        logger.info(
            "Scan started",
            extra={
                "extra_data": {
                    "scan_job_id": str(scan_job_id),
                    "subnet_cidr": subnet.cidr,
                    "triggered_by": job.triggered_by.value,
                }
            },
        )

        # Execute discovery probe asynchronously outside DB transaction
        try:
            probe_results = await self.scanner.scan_cidr(subnet_cidr, scan_ports=True)
        except Exception as e:
            duration_ms = int((time.monotonic() - scan_start) * 1000)
            logger.error(
                "Scan failed",
                extra={
                    "extra_data": {
                        "scan_job_id": str(scan_job_id),
                        "subnet_cidr": subnet.cidr,
                        "error": str(e),
                        "duration_ms": duration_ms,
                    }
                },
            )
            with Session(engine) as session:
                job = session.get(ScanJob, scan_job_id)
                if job:
                    job.status = ScanStatus.FAILED
                    job.error_message = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    session.add(job)
                    session.commit()
            return

        # Reconcile probe results against existing IP records
        with Session(engine) as session:
            subnet = session.get(Subnet, job_subnet_id)
            all_hosts = expand_cidr_hosts(subnet.cidr)

            # Fetch existing IP records for this subnet
            existing_ips_query = select(IPAddress).where(IPAddress.subnet_id == subnet.id)
            existing_ips_map: Dict[str, IPAddress] = {
                ip_rec.ip: ip_rec for ip_rec in session.exec(existing_ips_query).all()
            }

            now = datetime.now(timezone.utc)
            active_count = 0
            uncertain_count = 0
            available_count = 0
            reserved_count = 0
            state_change_events: List[Dict] = []

            for ip_str in all_hosts:
                existing_rec = existing_ips_map.get(ip_str)
                probe = probe_results.get(ip_str)

                outcome = StateClassifier.classify(
                    ip=ip_str,
                    existing=existing_rec,
                    probe=probe,
                    subnet=subnet,
                    now=now,
                )

                if existing_rec is None:
                    ip_obj = IPAddress(
                        subnet_id=subnet.id,
                        ip=ip_str,
                        status=outcome.new_status,
                        hostname=outcome.hostname,
                        mac_address=outcome.mac_address,
                        mac_vendor=outcome.mac_vendor,
                        open_ports=outcome.open_ports,
                        discovery_method=outcome.discovery_method,
                        consecutive_misses=outcome.consecutive_misses,
                        first_seen_at=outcome.first_seen_at,
                        last_seen_at=outcome.last_seen_at,
                        last_scanned_at=outcome.last_scanned_at,
                    )
                    session.add(ip_obj)
                    session.flush()  # Generate id
                    target_ip_id = ip_obj.id
                else:
                    ip_obj = existing_rec
                    ip_obj.status = outcome.new_status
                    ip_obj.hostname = outcome.hostname
                    ip_obj.mac_address = outcome.mac_address
                    ip_obj.mac_vendor = outcome.mac_vendor
                    ip_obj.open_ports = outcome.open_ports
                    ip_obj.discovery_method = outcome.discovery_method
                    ip_obj.consecutive_misses = outcome.consecutive_misses
                    ip_obj.first_seen_at = outcome.first_seen_at
                    ip_obj.last_seen_at = outcome.last_seen_at
                    ip_obj.last_scanned_at = outcome.last_scanned_at
                    ip_obj.updated_at = now
                    session.add(ip_obj)
                    target_ip_id = ip_obj.id

                # Audit Logging for changes
                if outcome.event_type:
                    history_entry = IPHistory(
                        ip_address_id=target_ip_id,
                        event_type=outcome.event_type,
                        old_status=outcome.old_status.value if outcome.old_status else None,
                        new_status=outcome.new_status.value,
                        probe_details=outcome.event_details or {},
                        timestamp=now,
                    )
                    session.add(history_entry)

                    if outcome.state_changed:
                        state_change_events.append(
                            {
                                "ip": ip_str,
                                "old_status": outcome.old_status.value if outcome.old_status else None,
                                "new_status": outcome.new_status.value,
                                "hostname": outcome.hostname,
                                "mac_address": outcome.mac_address,
                                "open_ports": outcome.open_ports,
                                "subnet_cidr": subnet.cidr,
                            }
                        )

                # Tally stats
                if outcome.new_status == IPStatus.ACTIVE_DETECTED:
                    active_count += 1
                elif outcome.new_status == IPStatus.UNCERTAIN_FIREWALLED:
                    uncertain_count += 1
                elif outcome.new_status == IPStatus.AVAILABLE_CANDIDATE:
                    available_count += 1
                elif outcome.new_status == IPStatus.ASSIGNED_RESERVED:
                    reserved_count += 1

            # Update job record
            job = session.get(ScanJob, scan_job_id)
            job.status = ScanStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.total_ips = len(all_hosts)
            job.active_ips = active_count
            job.uncertain_ips = uncertain_count
            job.available_ips = available_count
            job.reserved_ips = reserved_count
            session.add(job)
            session.commit()

            duration_ms = int((time.monotonic() - scan_start) * 1000)
            logger.info(
                "Scan completed",
                extra={
                    "extra_data": {
                        "scan_job_id": str(scan_job_id),
                        "subnet_cidr": subnet.cidr,
                        "total_ips": job.total_ips,
                        "active_ips": active_count,
                        "uncertain_ips": uncertain_count,
                        "available_ips": available_count,
                        "reserved_ips": reserved_count,
                        "duration_ms": duration_ms,
                    }
                },
            )

            # Dispatch webhooks asynchronously
            for evt in state_change_events:
                task = asyncio.create_task(WebhookDispatcher.dispatch_event("ip.state_changed", evt, session))
                task.add_done_callback(_track_webhook_task)
                _webhook_tasks.add(task)

            task = asyncio.create_task(
                WebhookDispatcher.dispatch_event(
                    "scan.completed",
                    {
                        "scan_job_id": str(job.id),
                        "subnet_id": str(subnet.id),
                        "subnet_cidr": subnet.cidr,
                        "total_ips": job.total_ips,
                        "active_ips": job.active_ips,
                        "uncertain_ips": job.uncertain_ips,
                        "available_ips": job.available_ips,
                        "reserved_ips": job.reserved_ips,
                    },
                    session,
                )
            )
            task.add_done_callback(_track_webhook_task)
            _webhook_tasks.add(task)


scan_service = ScanService()
