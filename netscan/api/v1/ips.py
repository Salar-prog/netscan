import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, col, select
from netscan.api.auth import get_current_api_key, require_role
from netscan.db import get_session
from netscan.models import (
    EventType,
    IPAddress,
    IPHistory,
    IPStatus,
    Role,
    Subnet,
    utc_now,
)

router = APIRouter(prefix="/ips", tags=["IP Addresses"])


class IPReservationUpdate(BaseModel):
    is_reserved: bool
    custom_metadata: Optional[Dict[str, Any]] = None
    hostname: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]])
def list_ips(
    subnet_id: Optional[uuid.UUID] = None,
    status_filter: Optional[IPStatus] = None,
    hostname_search: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    statement = select(IPAddress)
    if subnet_id:
        statement = statement.where(IPAddress.subnet_id == subnet_id)
    if status_filter:
        statement = statement.where(IPAddress.status == status_filter)
    if hostname_search:
        statement = statement.where(col(IPAddress.hostname).ilike(f"%{hostname_search}%"))

    statement = statement.offset(offset).limit(limit)
    ips = session.exec(statement).all()

    return [
        {
            "id": ip.id,
            "ip": ip.ip,
            "subnet_id": ip.subnet_id,
            "status": ip.status.value,
            "hostname": ip.hostname,
            "mac_address": ip.mac_address,
            "mac_vendor": ip.mac_vendor,
            "open_ports": ip.open_ports,
            "discovery_method": ip.discovery_method.value,
            "consecutive_misses": ip.consecutive_misses,
            "first_seen_at": ip.first_seen_at,
            "last_seen_at": ip.last_seen_at,
            "last_scanned_at": ip.last_scanned_at,
            "custom_metadata": ip.custom_metadata,
        }
        for ip in ips
    ]


@router.get("/available")
def get_available_ips(
    subnet_id: uuid.UUID,
    count: int = Query(default=1, ge=1, le=50),
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    """Retrieve the next K available IPs in a subnet for automated deployment / provisioning."""
    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    from netscan.scanner.cidr import expand_cidr_hosts
    all_hosts = expand_cidr_hosts(subnet.cidr)

    # Get non-available IPs
    unavailable_query = select(IPAddress).where(
        IPAddress.subnet_id == subnet.id,
        IPAddress.status.in_([IPStatus.ACTIVE_DETECTED, IPStatus.ASSIGNED_RESERVED, IPStatus.UNCERTAIN_FIREWALLED]),
    )
    unavailable_ips = {rec.ip for rec in session.exec(unavailable_query).all()}

    available_candidates: List[str] = []
    for host in all_hosts:
        if host not in unavailable_ips:
            available_candidates.append(host)
            if len(available_candidates) >= count:
                break

    return {
        "subnet_id": subnet.id,
        "cidr": subnet.cidr,
        "requested_count": count,
        "available_ips": available_candidates,
        "count_returned": len(available_candidates),
    }


@router.get("/{ip_address}")
def get_ip_detail(
    ip_address: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    rec = session.exec(select(IPAddress).where(IPAddress.ip == ip_address.strip())).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"IP '{ip_address}' not tracked yet.")
    return rec


@router.patch("/{ip_address}")
def update_ip_reservation(
    ip_address: str,
    payload: IPReservationUpdate,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    """Reserve, unreserve, or attach custom metadata to an IP."""
    rec = session.exec(select(IPAddress).where(IPAddress.ip == ip_address.strip())).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"IP '{ip_address}' not found.")

    old_status = rec.status
    now = utc_now()

    if payload.is_reserved:
        rec.status = IPStatus.ASSIGNED_RESERVED
    elif rec.status == IPStatus.ASSIGNED_RESERVED:
        rec.status = IPStatus.AVAILABLE_CANDIDATE

    if payload.hostname is not None:
        rec.hostname = payload.hostname
    if payload.custom_metadata is not None:
        rec.custom_metadata = payload.custom_metadata

    rec.updated_at = now
    session.add(rec)

    # Add audit log
    if old_status != rec.status:
        history = IPHistory(
            ip_address_id=rec.id,
            event_type=EventType.RESERVED_TOGGLE,
            old_status=old_status.value,
            new_status=rec.status.value,
            probe_details={"updated_by": "api_user", "custom_metadata": rec.custom_metadata},
            timestamp=now,
        )
        session.add(history)

    session.commit()
    session.refresh(rec)
    return rec


@router.get("/{ip_address}/history")
def get_ip_history(
    ip_address: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    rec = session.exec(select(IPAddress).where(IPAddress.ip == ip_address.strip())).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"IP '{ip_address}' not found.")

    history = session.exec(
        select(IPHistory)
        .where(IPHistory.ip_address_id == rec.id)
        .order_by(IPHistory.timestamp.desc())
    ).all()

    return {
        "ip": rec.ip,
        "current_status": rec.status.value,
        "timeline": history,
    }
