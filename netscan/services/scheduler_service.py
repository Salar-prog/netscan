import logging
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select
from netscan.db import engine
from netscan.models import ScanJob, ScanStatus, Subnet, TriggerType
from netscan.services.scan_service import scan_service

logger = logging.getLogger(__name__)


class ScanScheduler:
    """Manages recurring automated scans via in-process APScheduler."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            self.sync_all_subnet_jobs()
            job_count = len(self.scheduler.get_jobs())
            logger.info("Scheduler started", extra={"extra_data": {"job_count": job_count}})

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped.")

    def sync_all_subnet_jobs(self) -> None:
        """Register recurring jobs for all active subnets with interval > 0."""
        with Session(engine) as session:
            subnets = session.exec(select(Subnet).where(Subnet.is_active)).all()
            for subnet in subnets:
                self.update_subnet_job(subnet)

    def update_subnet_job(self, subnet: Subnet) -> None:
        """Add or update an interval scan job for a specific subnet."""
        job_id = f"subnet_scan_{subnet.id}"

        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed scheduler job", extra={"extra_data": {"job_id": job_id, "subnet_cidr": subnet.cidr}})

        if subnet.is_active and subnet.scan_interval_minutes > 0:
            self.scheduler.add_job(
                func=self.trigger_scheduled_scan,
                trigger="interval",
                minutes=subnet.scan_interval_minutes,
                id=job_id,
                args=[subnet.id],
                replace_existing=True,
            )
            logger.info(
                "Scheduled scan",
                extra={
                    "extra_data": {
                        "subnet_cidr": subnet.cidr,
                        "interval_minutes": subnet.scan_interval_minutes,
                        "job_id": job_id,
                    }
                },
            )

    def remove_subnet_job(self, subnet_id: uuid.UUID) -> None:
        job_id = f"subnet_scan_{subnet_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed scheduler job", extra={"extra_data": {"job_id": job_id}})

    @staticmethod
    async def trigger_scheduled_scan(subnet_id: uuid.UUID) -> None:
        try:
            with Session(engine) as session:
                job = ScanJob(
                    subnet_id=subnet_id,
                    status=ScanStatus.QUEUED,
                    triggered_by=TriggerType.SCHEDULE,
                )
                session.add(job)
                session.commit()
                session.refresh(job)
                scan_job_id = job.id

            await scan_service.execute_scan(scan_job_id)
        except Exception as e:
            logger.error(
                "Scheduled scan failed",
                extra={"extra_data": {"subnet_id": str(subnet_id), "error": str(e)}},
            )


scheduler = ScanScheduler()
