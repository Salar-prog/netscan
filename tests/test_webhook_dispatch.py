"""F18: Test webhook dispatch from scan execution."""
import asyncio
import uuid
from unittest.mock import patch, AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from netscan.models import IPAddress, IPStatus, ScanJob, ScanStatus, Subnet, TriggerType, Webhook
from netscan.services.scan_service import ScanService, _webhook_tasks
from netscan.services.webhook_service import WebhookDispatcher


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="patch_scanner")
def patch_scanner_fixture():
    """Mock NmapScanner.scan_cidr to return fake results."""
    from netscan.scanner.runner import HostProbeResult, PortInfo
    from netscan.models import DiscoveryMethod

    async def fake_scan(cidr, scan_ports=True):
        results = {}
        results["10.0.0.1"] = HostProbeResult(
            ip="10.0.0.1", is_up=True, status_reason="syn-ack",
            hostname="host1", open_ports=[PortInfo(port=80, state="open", protocol="tcp", service="http")],
            discovery_method=DiscoveryMethod.TCP_CONNECT, mac_address=None, mac_vendor=None,
        )
        results["10.0.0.2"] = HostProbeResult(
            ip="10.0.0.2", is_up=False, status_reason="no-response",
            hostname="", open_ports=[],
            discovery_method=DiscoveryMethod.TCP_CONNECT, mac_address=None, mac_vendor=None,
        )
        return results

    with patch("netscan.services.scan_service.NmapScanner") as mock_cls:
        mock_instance = mock_cls.return_value
        mock_instance.scan_cidr = AsyncMock(side_effect=fake_scan)
        yield


@pytest.fixture(name="patch_dispatch")
def patch_dispatch_fixture():
    """Track webhook dispatch calls."""
    calls = []
    original_dispatch = WebhookDispatcher.dispatch_event

    async def tracking_dispatch(event, data, session):
        calls.append({"event": event, "data": data})
        return await original_dispatch(event, data, session)

    with patch.object(WebhookDispatcher, "dispatch_event", side_effect=tracking_dispatch):
        yield calls


async def test_scan_dispatches_webhooks(db_engine, patch_scanner, patch_dispatch):
    """Execute a scan and verify webhook dispatch is called for state changes and scan.completed."""
    import netscan.services.scan_service as ss

    ss.engine = db_engine

    with Session(db_engine) as session:
        subnet = Subnet(
            cidr="10.0.0.0/30",
            name="test-subnet",
            scan_interval_minutes=60,
            miss_threshold=3,
            quarantine_hours=48,
            is_active=True,
        )
        session.add(subnet)
        session.commit()
        session.refresh(subnet)

        wh = Webhook(
            id=uuid.uuid4(),
            name="test-hook",
            url="https://example.com/hook",
            secret="test-secret",
            events=["*"],
            is_active=True,
        )
        session.add(wh)
        session.commit()

        job = ScanJob(
            subnet_id=subnet.id,
            status=ScanStatus.QUEUED,
            triggered_by=TriggerType.MANUAL_UI,
        )
        session.add(job)
        session.commit()
        session.refresh(job)

    # Instantiate AFTER patching NmapScanner
    scan_service = ScanService()
    await scan_service.execute_scan(job.id)

    # Wait for fire-and-forget webhook tasks to complete
    if _webhook_tasks:
        await asyncio.gather(*_webhook_tasks, return_exceptions=True)

    # Verify dispatch was called
    assert len(patch_dispatch) >= 1
    events = [c["event"] for c in patch_dispatch]
    assert "scan.completed" in events

    # Verify job completed
    with Session(db_engine) as session:
        completed_job = session.get(ScanJob, job.id)
        assert completed_job.status == ScanStatus.COMPLETED
