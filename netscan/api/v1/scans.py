import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from netscan.api.auth import get_current_api_key
from netscan.api.v1.router import NetScanException
from netscan.db import get_session
from netscan.models import ScanJob

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.get("", response_model=List[ScanJob])
def list_scans(
    subnet_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    statement = select(ScanJob)
    if subnet_id:
        statement = statement.where(ScanJob.subnet_id == subnet_id)
    statement = statement.order_by(ScanJob.created_at.desc()).limit(limit)
    return session.exec(statement).all()


@router.get("/{scan_id}", response_model=ScanJob)
def get_scan(
    scan_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    job = session.get(ScanJob, scan_id)
    if not job:
        raise NetScanException("SCAN_NOT_FOUND", "Scan job not found", status_code=404)
    return job
