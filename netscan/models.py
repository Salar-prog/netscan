import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from sqlmodel import Column, Field, JSON, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IPStatus(str, Enum):
    ACTIVE_DETECTED = "ACTIVE_DETECTED"
    AVAILABLE_CANDIDATE = "AVAILABLE_CANDIDATE"
    ASSIGNED_RESERVED = "ASSIGNED_RESERVED"
    UNCERTAIN_FIREWALLED = "UNCERTAIN_FIREWALLED"


class DiscoveryMethod(str, Enum):
    ARP = "ARP"
    ICMP = "ICMP"
    TCP_SYN = "TCP_SYN"
    TCP_CONNECT = "TCP_CONNECT"
    DNS_ONLY = "DNS_ONLY"
    MANUAL = "MANUAL"
    NONE = "NONE"


class ScanStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TriggerType(str, Enum):
    SCHEDULE = "SCHEDULE"
    MANUAL_API = "MANUAL_API"
    MANUAL_UI = "MANUAL_UI"


class EventType(str, Enum):
    DISCOVERED = "DISCOVERED"
    STATE_CHANGE = "STATE_CHANGE"
    PORT_CHANGE = "PORT_CHANGE"
    RESERVED_TOGGLE = "RESERVED_TOGGLE"
    METADATA_UPDATE = "METADATA_UPDATE"


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    READ_ONLY = "read_only"


# ---------------------------------------------------------------------------
# Database Tables
# ---------------------------------------------------------------------------


class Subnet(SQLModel, table=True):
    __tablename__ = "subnets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    cidr: str = Field(index=True, unique=True, description="IPv4 CIDR block (e.g. 192.168.1.0/24)")
    name: str = Field(index=True)
    description: Optional[str] = None
    scan_interval_minutes: int = Field(default=60, description="0 disables scheduled scanning")
    miss_threshold: int = Field(default=3, description="Consecutive missed scans before eligible for available")
    quarantine_hours: int = Field(default=48, description="Minimum hours in UNCERTAIN before becoming AVAILABLE")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    ips: List["IPAddress"] = Relationship(back_populates="subnet", cascade_delete=True)
    scans: List["ScanJob"] = Relationship(back_populates="subnet", cascade_delete=True)


class IPAddress(SQLModel, table=True):
    __tablename__ = "ip_addresses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subnet_id: uuid.UUID = Field(foreign_key="subnets.id", index=True)
    ip: str = Field(index=True, description="IPv4 address string")
    status: IPStatus = Field(default=IPStatus.AVAILABLE_CANDIDATE, index=True)
    hostname: Optional[str] = Field(default=None, index=True)
    mac_address: Optional[str] = Field(default=None, index=True)
    mac_vendor: Optional[str] = None
    open_ports: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    discovery_method: DiscoveryMethod = Field(default=DiscoveryMethod.NONE)
    consecutive_misses: int = Field(default=0)
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_scanned_at: Optional[datetime] = None
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    subnet: Optional[Subnet] = Relationship(back_populates="ips")
    history: List["IPHistory"] = Relationship(back_populates="ip_address", cascade_delete=True)


class ScanJob(SQLModel, table=True):
    __tablename__ = "scan_jobs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subnet_id: uuid.UUID = Field(foreign_key="subnets.id", index=True)
    status: ScanStatus = Field(default=ScanStatus.QUEUED, index=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_ips: int = Field(default=0)
    active_ips: int = Field(default=0)
    uncertain_ips: int = Field(default=0)
    available_ips: int = Field(default=0)
    reserved_ips: int = Field(default=0)
    error_message: Optional[str] = None
    triggered_by: TriggerType = Field(default=TriggerType.SCHEDULE)
    created_at: datetime = Field(default_factory=utc_now)

    # Relationships
    subnet: Optional[Subnet] = Relationship(back_populates="scans")


class IPHistory(SQLModel, table=True):
    __tablename__ = "ip_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ip_address_id: uuid.UUID = Field(foreign_key="ip_addresses.id", index=True)
    event_type: EventType = Field(index=True)
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    probe_details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=utc_now, index=True)

    # Relationships
    ip_address: Optional[IPAddress] = Relationship(back_populates="history")


class Webhook(SQLModel, table=True):
    __tablename__ = "webhooks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    url: str
    secret: str
    events: List[str] = Field(default_factory=lambda: ["ip.state_changed", "scan.completed"], sa_column=Column(JSON))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    key_hash: str = Field(index=True, unique=True)
    prefix: str = Field(index=True)
    role: Role = Field(default=Role.OPERATOR)
    is_active: bool = Field(default=True)
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class IdempotencyRecord(SQLModel, table=True):
    __tablename__ = "idempotency_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    idempotency_key: str = Field(index=True, unique=True)
    endpoint: str
    request_hash: str
    status_code: int
    response_body: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
