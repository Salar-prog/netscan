import uuid
from datetime import datetime, timedelta, timezone
from netscan.models import DiscoveryMethod, IPAddress, IPStatus, Subnet
from netscan.scanner.classifier import StateClassifier
from netscan.scanner.runner import HostProbeResult, PortInfo


def make_subnet(miss_threshold: int = 3, quarantine_hours: int = 48) -> Subnet:
    return Subnet(
        id=uuid.uuid4(),
        cidr="192.168.1.0/24",
        name="Test Subnet",
        miss_threshold=miss_threshold,
        quarantine_hours=quarantine_hours,
    )


def test_positive_probe_activates_host():
    subnet = make_subnet()
    now = datetime.now(timezone.utc)

    probe = HostProbeResult(
        ip="192.168.1.10",
        is_up=True,
        status_reason="arp-response",
        discovery_method=DiscoveryMethod.ARP,
        hostname="router.local",
        mac_address="AA:BB:CC:DD:EE:FF",
        mac_vendor="Cisco Systems",
        open_ports=[PortInfo(port=80, protocol="tcp", state="open", service="http")],
    )

    outcome = StateClassifier.classify(
        ip="192.168.1.10",
        existing=None,
        probe=probe,
        subnet=subnet,
        now=now,
    )

    assert outcome.new_status == IPStatus.ACTIVE_DETECTED
    assert outcome.state_changed is True
    assert outcome.hostname == "router.local"
    assert outcome.mac_address == "AA:BB:CC:DD:EE:FF"
    assert outcome.mac_vendor == "Cisco Systems"
    assert len(outcome.open_ports) == 1
    assert outcome.consecutive_misses == 0


def test_active_host_becomes_uncertain_on_first_miss():
    subnet = make_subnet()
    now = datetime.now(timezone.utc)

    existing = IPAddress(
        id=uuid.uuid4(),
        subnet_id=subnet.id,
        ip="192.168.1.10",
        status=IPStatus.ACTIVE_DETECTED,
        hostname="server1.local",
        consecutive_misses=0,
        last_seen_at=now - timedelta(hours=1),
    )

    outcome = StateClassifier.classify(
        ip="192.168.1.10",
        existing=existing,
        probe=None,
        subnet=subnet,
        now=now,
    )

    assert outcome.new_status == IPStatus.UNCERTAIN_FIREWALLED
    assert outcome.state_changed is True
    assert outcome.consecutive_misses == 1
    assert outcome.hostname == "server1.local"


def test_uncertain_host_remains_uncertain_if_quarantine_not_met():
    subnet = make_subnet(miss_threshold=3, quarantine_hours=48)
    now = datetime.now(timezone.utc)

    existing = IPAddress(
        id=uuid.uuid4(),
        subnet_id=subnet.id,
        ip="192.168.1.10",
        status=IPStatus.UNCERTAIN_FIREWALLED,
        consecutive_misses=2,
        last_seen_at=now - timedelta(hours=12),
    )

    outcome = StateClassifier.classify(
        ip="192.168.1.10",
        existing=existing,
        probe=None,
        subnet=subnet,
        now=now,
    )

    assert outcome.new_status == IPStatus.UNCERTAIN_FIREWALLED
    assert outcome.state_changed is False
    assert outcome.consecutive_misses == 3


def test_uncertain_host_becomes_available_when_quarantine_and_misses_met():
    subnet = make_subnet(miss_threshold=3, quarantine_hours=48)
    now = datetime.now(timezone.utc)

    existing = IPAddress(
        id=uuid.uuid4(),
        subnet_id=subnet.id,
        ip="192.168.1.10",
        status=IPStatus.UNCERTAIN_FIREWALLED,
        consecutive_misses=2,
        last_seen_at=now - timedelta(hours=50),
    )

    outcome = StateClassifier.classify(
        ip="192.168.1.10",
        existing=existing,
        probe=None,
        subnet=subnet,
        now=now,
    )

    assert outcome.new_status == IPStatus.AVAILABLE_CANDIDATE
    assert outcome.state_changed is True
    assert outcome.consecutive_misses == 3


def test_reserved_ip_retains_reserved_status():
    subnet = make_subnet()
    now = datetime.now(timezone.utc)

    existing = IPAddress(
        id=uuid.uuid4(),
        subnet_id=subnet.id,
        ip="192.168.1.1",
        status=IPStatus.ASSIGNED_RESERVED,
        hostname="gateway.corp",
        consecutive_misses=0,
    )

    outcome = StateClassifier.classify(
        ip="192.168.1.1",
        existing=existing,
        probe=None,
        subnet=subnet,
        now=now,
    )

    assert outcome.new_status == IPStatus.ASSIGNED_RESERVED
    assert outcome.state_changed is False
    assert outcome.consecutive_misses == 1
