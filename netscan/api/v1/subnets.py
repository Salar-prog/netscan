import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session, select
from netscan.api.auth import get_current_api_key, require_role
from netscan.api.v1.router import NetScanException
from netscan.db import get_session
from netscan.models import IPAddress, IPStatus, Role, ScanJob, ScanStatus, Subnet, TriggerType, utc_now
from netscan.scanner.cidr import expand_cidr_hosts, get_subnet_metadata, validate_and_normalize_cidr
from netscan.services.scan_service import check_active_scan, scan_service
from netscan.services.scheduler_service import scheduler

router = APIRouter(prefix="/subnets", tags=["Subnets"])


class SubnetCreate(BaseModel):
    cidr: str
    name: str
    description: Optional[str] = None
    scan_interval_minutes: int = 60
    miss_threshold: int = 3
    quarantine_hours: int = 48
    is_active: bool = True


class SubnetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scan_interval_minutes: Optional[int] = None
    miss_threshold: Optional[int] = None
    quarantine_hours: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("", response_model=List[Dict[str, Any]])
def list_subnets(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    subnets = session.exec(select(Subnet)).all()
    results = []
    for s in subnets:
        # Calculate summary statistics for each subnet
        total_ips = len(expand_cidr_hosts(s.cidr))
        active_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.ACTIVE_DETECTED)
            ).all()
        )
        uncertain_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.UNCERTAIN_FIREWALLED)
            ).all()
        )
        reserved_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.ASSIGNED_RESERVED)
            ).all()
        )
        available_count = total_ips - (active_count + uncertain_count + reserved_count)

        meta = get_subnet_metadata(s.cidr)
        results.append(
            {
                "id": s.id,
                "cidr": s.cidr,
                "name": s.name,
                "description": s.description,
                "scan_interval_minutes": s.scan_interval_minutes,
                "miss_threshold": s.miss_threshold,
                "quarantine_hours": s.quarantine_hours,
                "is_active": s.is_active,
                "created_at": s.created_at,
                "metadata": meta,
                "stats": {
                    "total": total_ips,
                    "active": active_count,
                    "uncertain": uncertain_count,
                    "reserved": reserved_count,
                    "available": max(0, available_count),
                },
            }
        )
    return results


@router.post("", status_code=status.HTTP_201_CREATED)
def create_subnet(
    payload: SubnetCreate,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    try:
        norm_cidr = validate_and_normalize_cidr(payload.cidr)
    except ValueError as e:
        raise NetScanException("INVALID_CIDR", str(e), status_code=400)

    existing = session.exec(select(Subnet).where(Subnet.cidr == norm_cidr)).first()
    if existing:
        raise NetScanException("SUBNET_EXISTS", f"Subnet '{norm_cidr}' already exists.", status_code=400)

    subnet = Subnet(
        cidr=norm_cidr,
        name=payload.name,
        description=payload.description,
        scan_interval_minutes=payload.scan_interval_minutes,
        miss_threshold=payload.miss_threshold,
        quarantine_hours=payload.quarantine_hours,
        is_active=payload.is_active,
    )
    session.add(subnet)
    session.commit()
    session.refresh(subnet)

    # Register in scheduler
    scheduler.update_subnet_job(subnet)
    return subnet


@router.get("/{subnet_id}")
def get_subnet(
    subnet_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise NetScanException("SUBNET_NOT_FOUND", "Subnet not found", status_code=404)
    return subnet


@router.patch("/{subnet_id}")
def update_subnet(
    subnet_id: uuid.UUID,
    payload: SubnetUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise NetScanException("SUBNET_NOT_FOUND", "Subnet not found", status_code=404)

    update_dict = payload.model_dump(exclude_unset=True)
    for k, v in update_dict.items():
        setattr(subnet, k, v)
    subnet.updated_at = utc_now()
    session.add(subnet)
    session.commit()
    session.refresh(subnet)

    scheduler.update_subnet_job(subnet)
    return subnet


@router.delete("/{subnet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subnet(
    subnet_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise NetScanException("SUBNET_NOT_FOUND", "Subnet not found", status_code=404)

    scheduler.remove_subnet_job(subnet.id)
    session.delete(subnet)
    session.commit()
    return None


@router.get("/{subnet_id}/matrix")
def get_subnet_ip_matrix(
    subnet_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    """Return all IP addresses in the subnet with current real-time state for visual grid."""
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise NetScanException("SUBNET_NOT_FOUND", "Subnet not found", status_code=404)

    all_hosts = expand_cidr_hosts(subnet.cidr)
    existing_ips = session.exec(select(IPAddress).where(IPAddress.subnet_id == subnet.id)).all()
    ip_map = {ip_rec.ip: ip_rec for ip_rec in existing_ips}

    matrix = []
    for host_ip in all_hosts:
        rec = ip_map.get(host_ip)
        if rec:
            matrix.append(
                {
                    "ip": host_ip,
                    "status": rec.status.value,
                    "hostname": rec.hostname,
                    "mac_address": rec.mac_address,
                    "mac_vendor": rec.mac_vendor,
                    "open_ports_count": len(rec.open_ports),
                    "last_seen_at": rec.last_seen_at,
                    "last_scanned_at": rec.last_scanned_at,
                    "consecutive_misses": rec.consecutive_misses,
                }
            )
        else:
            matrix.append(
                {
                    "ip": host_ip,
                    "status": IPStatus.AVAILABLE_CANDIDATE.value,
                    "hostname": None,
                    "mac_address": None,
                    "mac_vendor": None,
                    "open_ports_count": 0,
                    "last_seen_at": None,
                    "last_scanned_at": None,
                    "consecutive_misses": 0,
                }
            )

    return {
        "subnet_id": subnet.id,
        "cidr": subnet.cidr,
        "name": subnet.name,
        "total_hosts": len(all_hosts),
        "matrix": matrix,
    }


@router.post("/{subnet_id}/scan")
async def trigger_subnet_scan(
    subnet_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    """Trigger an immediate asynchronous scan job for this subnet."""
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise NetScanException("SUBNET_NOT_FOUND", "Subnet not found", status_code=404)

    active_job = check_active_scan(session, subnet.id)
    if active_job:
        raise NetScanException(
            "SCAN_ALREADY_RUNNING",
            f"Scan already in progress for subnet {subnet.cidr} (job {active_job.id}).",
            status_code=409,
        )

    job = ScanJob(
        subnet_id=subnet.id,
        status=ScanStatus.QUEUED,
        triggered_by=TriggerType.MANUAL_API,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    # Launch background async scan
    asyncio.create_task(scan_service.execute_scan(job.id))
    return {
        "message": f"Scan queued for subnet {subnet.cidr}",
        "scan_job_id": job.id,
        "status": job.status,
    }
