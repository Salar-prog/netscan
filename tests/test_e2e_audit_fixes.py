import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from netscan.config import settings
from netscan.db import get_session
from netscan.main import app
from netscan.models import IPAddress


@pytest.fixture(name="e2e_client")
def e2e_client_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as client:
        res = client.post("/api/v1/auth/keys/bootstrap", json={"name": "e2e-admin"})
        raw_key = res.json()["raw_key"]
        yield client, {"X-API-Key": raw_key}, engine
    app.dependency_overrides.clear()


def test_full_lifecycle(e2e_client):
    client, headers, engine = e2e_client

    # 1. Bootstrap already done — verify key works
    res = client.get("/api/v1/subnets", headers=headers)
    assert res.status_code == 200
    assert res.json() == []

    # 2. Create a small subnet
    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.99.0.0/30", "name": "E2E Lifecycle Subnet"},
        headers=headers,
    )
    assert res.status_code == 201
    subnet = res.json()
    subnet_id = subnet["id"]
    assert subnet["cidr"] == "10.99.0.0/30"

    # Seed IP records (normally created by scan_service)
    with Session(engine) as session:
        for ip_addr in ["10.99.0.1", "10.99.0.2"]:
            session.add(IPAddress(subnet_id=uuid.UUID(subnet_id), ip=ip_addr))
        session.commit()

    # 3. List subnets (stats are on list response)
    res = client.get("/api/v1/subnets", headers=headers)
    assert res.status_code == 200
    listed = res.json()
    assert len(listed) == 1
    assert listed[0]["stats"]["total"] == 2

    # 4. Get subnet by ID
    res = client.get(f"/api/v1/subnets/{subnet_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["cidr"] == "10.99.0.0/30"

    # 5. Get CIDR matrix
    res = client.get(f"/api/v1/subnets/{subnet_id}/matrix", headers=headers)
    assert res.status_code == 200
    matrix = res.json()
    assert matrix["total_hosts"] == 2
    assert len(matrix["matrix"]) == 2
    assert all(ip["status"] == "AVAILABLE_CANDIDATE" for ip in matrix["matrix"])

    # 6. Get available IPs
    res = client.get(f"/api/v1/ips/available?subnet_id={subnet_id}&count=1", headers=headers)
    assert res.status_code == 200
    assert res.json()["count_returned"] == 1

    # 7. Reserve an IP
    res = client.patch(
        "/api/v1/ips/10.99.0.1",
        json={"is_reserved": True, "hostname": "e2e-test"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ASSIGNED_RESERVED"
    assert res.json()["hostname"] == "e2e-test"

    # 8. Check IP history
    res = client.get("/api/v1/ips/10.99.0.1/history", headers=headers)
    assert res.status_code == 200
    history = res.json()
    assert history["current_status"] == "ASSIGNED_RESERVED"
    assert len(history["timeline"]) == 1
    assert history["timeline"][0]["event_type"] == "RESERVED_TOGGLE"

    # 9. Unreserve the IP
    res = client.patch(
        "/api/v1/ips/10.99.0.1",
        json={"is_reserved": False},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "AVAILABLE_CANDIDATE"

    # 10. Create a webhook
    res = client.post(
        "/api/v1/webhooks",
        json={
            "name": "E2E Webhook",
            "url": "https://example.com/hook",
            "events": ["scan.completed"],
        },
        headers=headers,
    )
    assert res.status_code == 201
    wh = res.json()
    assert "secret" in wh

    # 11. List webhooks (verify secret is hidden)
    res = client.get("/api/v1/webhooks", headers=headers)
    assert res.status_code == 200
    listed = res.json()
    assert len(listed) == 1
    assert "secret" not in listed[0]

    # 12. Delete subnet
    res = client.delete(f"/api/v1/subnets/{subnet_id}", headers=headers)
    assert res.status_code == 204

    # 13. Verify deleted
    res = client.get(f"/api/v1/subnets/{subnet_id}", headers=headers)
    assert res.status_code == 404


def test_large_cidr_rejected(e2e_client):
    client, headers, _ = e2e_client

    large_cidrs = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "10.0.0.0/23"]
    for cidr in large_cidrs:
        res = client.post(
            "/api/v1/subnets",
            json={"cidr": cidr, "name": f"Large {cidr}"},
            headers=headers,
        )
        assert res.status_code == 400, f"Expected 400 for {cidr}, got {res.status_code}"
        assert "too large" in res.json()["detail"]


def test_normal_cidr_accepted(e2e_client):
    client, headers, _ = e2e_client

    normal_cidrs = ["192.168.1.0/24", "10.0.0.0/25", "172.16.0.0/30"]
    for cidr in normal_cidrs:
        res = client.post(
            "/api/v1/subnets",
            json={"cidr": cidr, "name": f"Normal {cidr}"},
            headers=headers,
        )
        assert res.status_code == 201, f"Expected 201 for {cidr}, got {res.status_code}: {res.text}"


def test_scan_concurrency_guard(e2e_client):
    client, headers, engine = e2e_client

    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.88.0.0/30", "name": "Concurrency Test"},
        headers=headers,
    )
    subnet_id = res.json()["id"]

    # Seed an active scan job directly
    from netscan.models import ScanJob, ScanStatus, TriggerType

    with Session(engine) as session:
        job = ScanJob(
            id=uuid.uuid4(),
            subnet_id=uuid.UUID(subnet_id),
            status=ScanStatus.RUNNING,
            triggered_by=TriggerType.MANUAL_API,
        )
        session.add(job)
        session.commit()

    # Second trigger should be rejected
    res = client.post(f"/api/v1/subnets/{subnet_id}/scan", headers=headers)
    assert res.status_code == 409
    assert "already in progress" in res.json()["detail"]


def test_webhook_ssrf_blocklist(e2e_client):
    client, headers, _ = e2e_client

    blocked_urls = [
        "http://127.0.0.1:8080/hook",
        "http://10.0.0.1/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://172.16.0.1/hook",
    ]

    for url in blocked_urls:
        res = client.post(
            "/api/v1/webhooks",
            json={"name": "SSRF Test", "url": url},
            headers=headers,
        )
        assert res.status_code == 400, f"Expected 400 for {url}"
        assert "private/internal" in res.json()["detail"]


def test_webhook_public_url_accepted(e2e_client):
    client, headers, _ = e2e_client

    res = client.post(
        "/api/v1/webhooks",
        json={"name": "Public Webhook", "url": "https://example.com/hook"},
        headers=headers,
    )
    assert res.status_code == 201
    assert res.json()["name"] == "Public Webhook"


def test_bootstrap_only_works_once(e2e_client):
    client, headers, _ = e2e_client

    # Bootstrap was already called in fixture — second call should fail
    res = client.post(
        "/api/v1/auth/keys/bootstrap",
        json={"name": "second-bootstrap"},
    )
    assert res.status_code == 403
    assert "already exist" in res.json()["detail"]


def test_read_only_cannot_trigger_scan(e2e_client):
    client, headers, _ = e2e_client

    # Create a read-only key
    res = client.post(
        "/api/v1/auth/keys",
        json={"name": "readonly", "role": "read_only"},
        headers=headers,
    )
    assert res.status_code == 201
    ro_headers = {"X-API-Key": res.json()["raw_key"]}

    # Create a subnet with admin key
    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.77.0.0/30", "name": "Read-Only Test"},
        headers=headers,
    )
    subnet_id = res.json()["id"]

    # Read-only CAN read
    res = client.get(f"/api/v1/subnets/{subnet_id}", headers=ro_headers)
    assert res.status_code == 200

    # Read-only CANNOT trigger scan
    res = client.post(f"/api/v1/subnets/{subnet_id}/scan", headers=ro_headers)
    assert res.status_code == 403

    # Read-only CANNOT create subnets
    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.77.1.0/30", "name": "Should Fail"},
        headers=ro_headers,
    )
    assert res.status_code == 403


def test_config_defaults():
    assert settings.MAX_SCAN_PREFIX_LENGTH == 24
    assert settings.TRUSTED_PROXIES == ""
    assert "127.0.0.0/8" in settings.WEBHOOK_BLOCKED_RANGES
    assert "10.0.0.0/8" in settings.WEBHOOK_BLOCKED_RANGES
    assert "169.254.169.254/32" in settings.WEBHOOK_BLOCKED_RANGES
