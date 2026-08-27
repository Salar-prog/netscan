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
        yield client, {"X-API-Key": raw_key}
    app.dependency_overrides.clear()


def test_idempotent_post_returns_same_response(e2e):
    client, headers = e2e
    key = str(uuid.uuid4())

    res1 = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.50.0.0/30", "name": "Idem Test"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert res1.status_code == 201
    body1 = res1.json()

    res2 = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.50.0.0/30", "name": "Idem Test"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert res2.status_code == 201
    assert res2.json() == body1

    # Only one subnet should exist
    res_list = client.get("/api/v1/subnets", headers=headers)
    assert len(res_list.json()) == 1


def test_idempotent_key_reuse_different_body_conflicts(e2e):
    client, headers = e2e
    key = str(uuid.uuid4())

    client.post(
        "/api/v1/subnets",
        json={"cidr": "10.51.0.0/30", "name": "First"},
        headers={**headers, "Idempotency-Key": key},
    )

    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.52.0.0/30", "name": "Different"},
        headers={**headers, "Idempotency-Key": key},
    )
    assert res.status_code == 409
    assert res.json()["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_no_idempotency_key_passes_through(e2e):
    client, headers = e2e

    res1 = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.53.0.0/30", "name": "No Key"},
        headers=headers,
    )
    res2 = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.53.0.0/30", "name": "No Key"},
        headers=headers,
    )
    # Without idempotency key, both create separate subnets (duplicate CIDR → 400)
    assert res1.status_code == 201
    assert res2.status_code == 400
