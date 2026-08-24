import sys
import uuid
import pytest
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool
from netscan.models import (
    DiscoveryMethod,
    EventType,
    IPAddress,
    IPHistory,
    IPStatus,
    ScanJob,
    ScanStatus,
    Subnet,
    TriggerType,
)
from netscan.scanner.runner import HostProbeResult, PortInfo
from netscan.services.scan_service import scan_service

scan_module = sys.modules["netscan.services.scan_service"]


class FakeScanner:
    """Replaces NmapScanner so tests never invoke the nmap binary."""

    def __init__(self, results=None, error=None):
        self.results = results or {}
        self.error = error

    async def scan_cidr(self, cidr, scan_ports=True):
        if self.error:
            raise self.error
        return self.results


def make_probe(ip):
    return HostProbeResult(
        ip=ip,
        is_up=True,
        status_reason="arp-response",
        discovery_method=DiscoveryMethod.ARP,
        hostname=f"host-{ip.split('.')[-1]}.local",
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_vendor="Cisco",
        open_ports=[PortInfo(port=80, protocol="tcp", state="open", service="http")],
    )


@pytest.fixture(name="db_engine")
def db_engine_fixture(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scan_module, "engine", engine)
    yield engine
    engine.dispose()


def create_subnet(db_engine, cidr="10.0.0.0/29"):
    with Session(db_engine) as session:
        subnet = Subnet(id=uuid.uuid4(), cidr=cidr, name="Lab")
        session.add(subnet)
        session.commit()
        return subnet.id


async def queue_job_and_execute(db_engine, subnet_id):
    with Session(db_engine) as session:
        job = ScanJob(
            subnet_id=subnet_id,
            status=ScanStatus.QUEUED,
            triggered_by=TriggerType.MANUAL_API,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id
    await scan_service.execute_scan(job_id)
    return job_id


async def test_successful_scan_creates_records_and_stats(db_engine, monkeypatch):
    subnet_id = create_subnet(db_engine)
    monkeypatch.setattr(
        scan_service, "scanner", FakeScanner(results={"10.0.0.1": make_probe("10.0.0.1")})
    )
    job_id = await queue_job_and_execute(db_engine, subnet_id)

    with Session(db_engine) as session:
        refreshed = session.get(ScanJob, job_id)
        assert refreshed.status == ScanStatus.COMPLETED
        assert refreshed.total_ips == 6
        assert refreshed.active_ips == 1
        assert refreshed.available_ips == 5
        assert refreshed.started_at is not None
        assert refreshed.completed_at is not None

        ips = session.exec(select(IPAddress)).all()
        assert len(ips) == 6
        active = [i for i in ips if i.ip == "10.0.0.1"][0]
        assert active.status == IPStatus.ACTIVE_DETECTED
        assert active.mac_address == "AA:BB:CC:DD:EE:FF"
        assert active.mac_vendor == "Cisco"
        assert len(active.open_ports) == 1
        assert active.discovery_method == DiscoveryMethod.ARP

        available = [i for i in ips if i.ip == "10.0.0.2"][0]
        assert available.status == IPStatus.AVAILABLE_CANDIDATE

        history = session.exec(select(IPHistory)).all()
        assert len(history) == 6
        discovered = session.exec(
            select(IPHistory).where(
                IPHistory.ip_address_id == active.id,
                IPHistory.event_type == EventType.DISCOVERED,
            )
        ).all()
        assert len(discovered) == 1
        assert discovered[0].new_status == IPStatus.ACTIVE_DETECTED.value


async def test_missing_subnet_marks_job_failed(db_engine):
    missing_subnet_id = uuid.uuid4()

    with Session(db_engine) as session:
        job = ScanJob(
            subnet_id=missing_subnet_id,
            status=ScanStatus.QUEUED,
            triggered_by=TriggerType.MANUAL_API,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    await scan_service.execute_scan(job_id)

    with Session(db_engine) as session:
        refreshed = session.get(ScanJob, job_id)
        assert refreshed.status == ScanStatus.FAILED
        assert "not found" in refreshed.error_message


async def test_scanner_exception_marks_job_failed(db_engine, monkeypatch):
    subnet_id = create_subnet(db_engine, cidr="10.1.0.0/30")
    monkeypatch.setattr(scan_service, "scanner", FakeScanner(error=RuntimeError("nmap exploded")))
    job_id = await queue_job_and_execute(db_engine, subnet_id)

    with Session(db_engine) as session:
        refreshed = session.get(ScanJob, job_id)
        assert refreshed.status == ScanStatus.FAILED
        assert "nmap exploded" in refreshed.error_message
        assert refreshed.completed_at is not None


async def test_second_scan_updates_existing_records_and_audits_state_change(
    db_engine, monkeypatch
):
    subnet_id = create_subnet(db_engine)

    monkeypatch.setattr(
        scan_service,
        "scanner",
        FakeScanner(results={"10.0.0.1": make_probe("10.0.0.1"), "10.0.0.2": make_probe("10.0.0.2")}),
    )
    first_job_id = await queue_job_and_execute(db_engine, subnet_id)

    with Session(db_engine) as session:
        rec = session.exec(select(IPAddress).where(IPAddress.ip == "10.0.0.2")).first()
        assert rec.status == IPStatus.ACTIVE_DETECTED

    monkeypatch.setattr(scan_service, "scanner", FakeScanner(results={}))
    second_job_id = await queue_job_and_execute(db_engine, subnet_id)

    with Session(db_engine) as session:
        refreshed = session.get(ScanJob, second_job_id)
        assert refreshed.status == ScanStatus.COMPLETED

        rec = session.exec(select(IPAddress).where(IPAddress.ip == "10.0.0.2")).first()
        assert rec.status == IPStatus.UNCERTAIN_FIREWALLED
        assert rec.consecutive_misses == 1

        change_events = session.exec(
            select(IPHistory).where(IPHistory.event_type == EventType.STATE_CHANGE)
        ).all()
        assert len(change_events) == 2
        for evt in change_events:
            assert evt.old_status == IPStatus.ACTIVE_DETECTED.value
            assert evt.new_status == IPStatus.UNCERTAIN_FIREWALLED.value
