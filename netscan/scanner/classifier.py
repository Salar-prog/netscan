"""Safe IP Availability Heuristic Classifier."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from netscan.models import DiscoveryMethod, EventType, IPAddress, IPStatus, Subnet
from netscan.scanner.runner import HostProbeResult


@dataclass
class ClassificationOutcome:
    ip: str
    new_status: IPStatus
    old_status: Optional[IPStatus]
    state_changed: bool
    consecutive_misses: int
    hostname: Optional[str]
    mac_address: Optional[str]
    mac_vendor: Optional[str]
    open_ports: List[Dict[str, Any]]
    discovery_method: DiscoveryMethod
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    last_scanned_at: datetime
    event_type: Optional[EventType] = None
    event_details: Optional[Dict[str, Any]] = None


class StateClassifier:
    """Evaluates probe outcomes against subnet quarantine policies."""

    @staticmethod
    def classify(
        ip: str,
        existing: Optional[IPAddress],
        probe: Optional[HostProbeResult],
        subnet: Subnet,
        now: Optional[datetime] = None,
    ) -> ClassificationOutcome:
        now = now or datetime.now(timezone.utc)
        old_status = existing.status if existing else None
        last_scanned_at = now

        open_ports = [
            {
                "port": p.port,
                "protocol": p.protocol,
                "state": p.state,
                "service": p.service,
                "product": p.product,
                "version": p.version,
                "reason": p.reason,
            }
            for p in (probe.open_ports if probe else [])
        ] if probe else (existing.open_ports if existing else [])

        # Case 1: Manual Reservation Lock
        if existing and existing.status == IPStatus.ASSIGNED_RESERVED:
            is_active_probe = (probe is not None and probe.is_up)
            consecutive_misses = 0 if is_active_probe else (existing.consecutive_misses + 1)
            last_seen = now if is_active_probe else existing.last_seen_at

            return ClassificationOutcome(
                ip=ip,
                new_status=IPStatus.ASSIGNED_RESERVED,
                old_status=old_status,
                state_changed=False,
                consecutive_misses=consecutive_misses,
                hostname=probe.hostname if (probe and probe.hostname) else existing.hostname,
                mac_address=probe.mac_address if (probe and probe.mac_address) else existing.mac_address,
                mac_vendor=probe.mac_vendor if (probe and probe.mac_vendor) else existing.mac_vendor,
                open_ports=open_ports,
                discovery_method=probe.discovery_method if probe else existing.discovery_method,
                first_seen_at=existing.first_seen_at,
                last_seen_at=last_seen,
                last_scanned_at=last_scanned_at,
                event_type=None,
                event_details={},
            )

        # Case 2: Positive Probe Response (Host is UP)
        if probe and probe.is_up:
            new_status = IPStatus.ACTIVE_DETECTED
            state_changed = (old_status != IPStatus.ACTIVE_DETECTED)
            first_seen = existing.first_seen_at if existing and existing.first_seen_at else now

            event_type = None
            if old_status is None:
                event_type = EventType.DISCOVERED
            elif state_changed:
                event_type = EventType.STATE_CHANGE

            return ClassificationOutcome(
                ip=ip,
                new_status=new_status,
                old_status=old_status,
                state_changed=state_changed,
                consecutive_misses=0,
                hostname=probe.hostname or (existing.hostname if existing else None),
                mac_address=probe.mac_address or (existing.mac_address if existing else None),
                mac_vendor=probe.mac_vendor or (existing.mac_vendor if existing else None),
                open_ports=open_ports,
                discovery_method=probe.discovery_method,
                first_seen_at=first_seen,
                last_seen_at=now,
                last_scanned_at=last_scanned_at,
                event_type=event_type,
                event_details={"reason": probe.status_reason, "method": probe.discovery_method.value},
            )

        # Case 3: Negative Probe (Host is DOWN or UNRESPONSIVE)
        miss_count = (existing.consecutive_misses + 1) if existing else 1
        first_seen = existing.first_seen_at if existing else None
        last_seen = existing.last_seen_at if existing else None
        hostname = existing.hostname if existing else None
        mac_addr = existing.mac_address if existing else None
        mac_vend = existing.mac_vendor if existing else None
        method = existing.discovery_method if existing else DiscoveryMethod.NONE

        if old_status == IPStatus.ACTIVE_DETECTED:
            new_status = IPStatus.UNCERTAIN_FIREWALLED
            return ClassificationOutcome(
                ip=ip,
                new_status=new_status,
                old_status=old_status,
                state_changed=True,
                consecutive_misses=miss_count,
                hostname=hostname,
                mac_address=mac_addr,
                mac_vendor=mac_vend,
                open_ports=open_ports,
                discovery_method=method,
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                last_scanned_at=last_scanned_at,
                event_type=EventType.STATE_CHANGE,
                event_details={"reason": "host_unresponsive_entered_uncertain"},
            )

        if old_status == IPStatus.UNCERTAIN_FIREWALLED:
            reference_time = last_seen or (existing.created_at if existing else now)
            if reference_time.tzinfo is None:
                reference_time = reference_time.replace(tzinfo=timezone.utc)
            hours_in_uncertain = (now - reference_time).total_seconds() / 3600.0

            meets_miss_threshold = miss_count >= subnet.miss_threshold
            meets_quarantine_hours = hours_in_uncertain >= subnet.quarantine_hours

            if meets_miss_threshold and meets_quarantine_hours:
                new_status = IPStatus.AVAILABLE_CANDIDATE
                return ClassificationOutcome(
                    ip=ip,
                    new_status=new_status,
                    old_status=old_status,
                    state_changed=True,
                    consecutive_misses=miss_count,
                    hostname=hostname,
                    mac_address=mac_addr,
                    mac_vendor=mac_vend,
                    open_ports=[],
                    discovery_method=method,
                    first_seen_at=first_seen,
                    last_seen_at=last_seen,
                    last_scanned_at=last_scanned_at,
                    event_type=EventType.STATE_CHANGE,
                    event_details={
                        "reason": f"quarantine_completed: {miss_count} misses, {hours_in_uncertain:.1f}h elapsed"
                    },
                )
            else:
                return ClassificationOutcome(
                    ip=ip,
                    new_status=IPStatus.UNCERTAIN_FIREWALLED,
                    old_status=old_status,
                    state_changed=False,
                    consecutive_misses=miss_count,
                    hostname=hostname,
                    mac_address=mac_addr,
                    mac_vendor=mac_vend,
                    open_ports=open_ports,
                    discovery_method=method,
                    first_seen_at=first_seen,
                    last_seen_at=last_seen,
                    last_scanned_at=last_scanned_at,
                    event_type=None,
                    event_details={},
                )

        return ClassificationOutcome(
            ip=ip,
            new_status=IPStatus.AVAILABLE_CANDIDATE,
            old_status=old_status,
            state_changed=(old_status != IPStatus.AVAILABLE_CANDIDATE),
            consecutive_misses=miss_count,
            hostname=hostname,
            mac_address=mac_addr,
            mac_vendor=mac_vend,
            open_ports=[],
            discovery_method=method,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            last_scanned_at=last_scanned_at,
            event_type=EventType.DISCOVERED if old_status is None else None,
            event_details={"reason": "unseen_or_available"},
        )
