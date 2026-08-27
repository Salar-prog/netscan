import sys
import uuid

import pytest
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool
from netscan.models import ScanJob, ScanStatus, Subnet, TriggerType
from netscan.services.scheduler_service import ScanScheduler

scheduler_module = sys.modules["netscan.services.scheduler_service"]


class FakeScanService:
    def __init__(self):
        self.executed = []

    async def execute_scan(self, scan_job_id):
        self.executed.append(scan_job_id)


@pytest.fixture(name="db_engine")
def db_engine_fixture(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler_module, "engine", engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="sched")
def sched_fixture():
    s = ScanScheduler()
    yield s
    s.shutdown()


def make_subnet(db_engine, cidr="10.0.0.0/29", is_active=True, interval=60):
    with Session(db_engine) as session:
        subnet = Subnet(
            id=uuid.uuid4(),
            cidr=cidr,
            name=f"Pool {cidr}",
            is_active=is_active,
            scan_interval_minutes=interval,
        )
        session.add(subnet)
        session.commit()
        session.refresh(subnet)
        return subnet


def test_update_subnet_job_schedules_active_subnet(db_engine, sched):
    subnet = make_subnet(db_engine)
    sched.update_subnet_job(subnet)

    job = sched.scheduler.get_job(f"subnet_scan_{subnet.id}")
    assert job is not None
    assert list(job.args) == [subnet.id]


def test_update_subnet_job_skips_inactive_subnet(db_engine, sched):
    subnet = make_subnet(db_engine, cidr="10.1.0.0/30", is_active=False)
    sched.update_subnet_job(subnet)

    assert sched.scheduler.get_job(f"subnet_scan_{subnet.id}") is None


def test_update_subnet_job_skips_manual_only_subnet(db_engine, sched):
    subnet = make_subnet(db_engine, cidr="10.2.0.0/30", interval=0)
    sched.update_subnet_job(subnet)

    assert sched.scheduler.get_job(f"subnet_scan_{subnet.id}") is None


def test_update_subnet_job_removes_job_when_disabled(db_engine, sched):
    subnet = make_subnet(db_engine)
    sched.update_subnet_job(subnet)
    assert sched.scheduler.get_job(f"subnet_scan_{subnet.id}") is not None

    subnet.is_active = False
    sched.update_subnet_job(subnet)
    assert sched.scheduler.get_job(f"subnet_scan_{subnet.id}") is None


def test_remove_subnet_job(db_engine, sched):
    subnet = make_subnet(db_engine, cidr="10.3.0.0/30")
    sched.update_subnet_job(subnet)

    sched.remove_subnet_job(subnet.id)
    assert sched.scheduler.get_job(f"subnet_scan_{subnet.id}") is None

    sched.remove_subnet_job(subnet.id)


async def test_trigger_scheduled_scan_creates_queued_job_and_executes(db_engine, sched, monkeypatch):
    fake = FakeScanService()
    monkeypatch.setattr(scheduler_module, "scan_service", fake)

    subnet = make_subnet(db_engine, cidr="10.4.0.0/30")
    await ScanScheduler.trigger_scheduled_scan(subnet.id)

    assert len(fake.executed) == 1

    with Session(db_engine) as session:
        jobs = session.exec(select(ScanJob)).all()
        assert len(jobs) == 1
        assert jobs[0].subnet_id == subnet.id
        assert jobs[0].status == ScanStatus.QUEUED
        assert jobs[0].triggered_by == TriggerType.SCHEDULE


async def test_trigger_scheduled_scan_skips_when_active_exists(db_engine, sched, monkeypatch):
    """Scheduler should skip creating a new job if one is already active."""
    fake = FakeScanService()
    monkeypatch.setattr(scheduler_module, "scan_service", fake)

    subnet = make_subnet(db_engine, cidr="10.5.0.0/30")

    # Seed an active RUNNING job
    with Session(db_engine) as session:
        active = ScanJob(
            subnet_id=subnet.id,
            status=ScanStatus.RUNNING,
            triggered_by=TriggerType.MANUAL_API,
        )
        session.add(active)
        session.commit()

    await ScanScheduler.trigger_scheduled_scan(subnet.id)

    # No new job should be created
    with Session(db_engine) as session:
        jobs = session.exec(select(ScanJob)).all()
        assert len(jobs) == 1  # only the original RUNNING job
        assert jobs[0].status == ScanStatus.RUNNING

    # execute_scan should NOT have been called
    assert len(fake.executed) == 0
