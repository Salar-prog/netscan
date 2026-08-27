import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select, func

from netscan.models import IPHistory, ScanJob

logger = logging.getLogger(__name__)


def prune_old_records(session: Session, retention_days: int) -> dict:
    """Delete ip_history and scan_jobs older than retention_days. Returns counts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    history_count = session.exec(select(func.count()).where(IPHistory.timestamp < cutoff)).one()
    for row in session.exec(select(IPHistory).where(IPHistory.timestamp < cutoff)).all():
        session.delete(row)

    job_count = session.exec(
        select(func.count()).where(ScanJob.created_at < cutoff, ScanJob.status.in_(["COMPLETED", "FAILED"]))
    ).one()
    for row in session.exec(
        select(ScanJob).where(ScanJob.created_at < cutoff, ScanJob.status.in_(["COMPLETED", "FAILED"]))
    ).all():
        session.delete(row)

    session.commit()
    logger.info(
        "Pruned %d history records and %d scan jobs older than %d days",
        history_count,
        job_count,
        retention_days,
    )
    return {"history_deleted": history_count, "jobs_deleted": job_count}
