import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from netscan.db import get_session
from netscan.main import app


@pytest.fixture(name="e2e")
def e2e_fixture():
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
        res = client.post("/api/v1/auth/keys/bootstrap", json={"name": "admin"})
        raw_key = res.json()["raw_key"]
        yield client, {"X-API-Key": raw_key}, engine
    app.dependency_overrides.clear()


def test_subnet_not_found_error_code(e2e):
    client, headers, _ = e2e
    fake_id = str(uuid.uuid4())
    res = client.get(f"/api/v1/subnets/{fake_id}", headers=headers)
    assert res.status_code == 404
    body = res.json()
    assert body["error_code"] == "SUBNET_NOT_FOUND"


def test_invalid_cidr_error_code(e2e):
    client, headers, _ = e2e
    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.0.0.0/8", "name": "Too Large"},
        headers=headers,
    )
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "INVALID_CIDR"
    assert "too large" in body["message"].lower()


def test_webhook_ssrf_error_code(e2e):
    client, headers, _ = e2e
    res = client.post(
        "/api/v1/webhooks",
        json={"name": "SSRF", "url": "http://169.254.169.254/latest"},
        headers=headers,
    )
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "SSRF_BLOCKED"


def test_bootstrap_disabled_error_code(e2e):
    client, headers, _ = e2e
    res = client.post(
        "/api/v1/auth/keys/bootstrap",
        json={"name": "second"},
    )
    assert res.status_code == 403
    body = res.json()
    assert body["error_code"] == "BOOTSTRAP_DISABLED"


def test_scan_already_running_error_code(e2e):
    client, headers, engine = e2e

    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.88.0.0/30", "name": "Err Envelope"},
        headers=headers,
    )
    subnet_id = res.json()["id"]

    from netscan.models import ScanJob, ScanStatus, TriggerType

    with Session(engine) as session:
        job = ScanJob(
            subnet_id=uuid.UUID(subnet_id),
            status=ScanStatus.RUNNING,
            triggered_by=TriggerType.MANUAL_API,
        )
        session.add(job)
        session.commit()

    res = client.post(f"/api/v1/subnets/{subnet_id}/scan", headers=headers)
    assert res.status_code == 409
    body = res.json()
    assert body["error_code"] == "SCAN_ALREADY_RUNNING"
    assert "message" in body
    assert "details" in body
