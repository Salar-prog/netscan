import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from netscan.db import get_session
from netscan.main import app
from netscan.models import IPStatus


@pytest.fixture(name="client")
def client_fixture():
    # Use in-memory SQLite for tests
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
        yield client
    app.dependency_overrides.clear()


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_subnet_crud_and_matrix(client: TestClient):
    create_payload = {
        "cidr": "10.10.0.0/29",
        "name": "Dev Lab Pool",
        "scan_interval_minutes": 30,
        "miss_threshold": 2,
        "quarantine_hours": 24,
    }
    res = client.post("/api/v1/subnets", json=create_payload)
    assert res.status_code == 201
    subnet_data = res.json()
    subnet_id = subnet_data["id"]
    assert subnet_data["cidr"] == "10.10.0.0/29"

    # Duplicate rejection
    dup_res = client.post("/api/v1/subnets", json=create_payload)
    assert dup_res.status_code == 400

    # List Subnets
    list_res = client.get("/api/v1/subnets")
    assert list_res.status_code == 200
    subnets = list_res.json()
    assert len(subnets) == 1
    assert subnets[0]["stats"]["total"] == 6

    # Get Matrix
    matrix_res = client.get(f"/api/v1/subnets/{subnet_id}/matrix")
    assert matrix_res.status_code == 200
    matrix_data = matrix_res.json()
    assert matrix_data["total_hosts"] == 6
    assert len(matrix_data["matrix"]) == 6
    assert matrix_data["matrix"][0]["status"] == "AVAILABLE_CANDIDATE"


def test_available_ips_query(client: TestClient):
    res = client.post("/api/v1/subnets", json={"cidr": "192.168.50.0/30", "name": "Point to Point"})
    subnet_id = res.json()["id"]

    avail_res = client.get(f"/api/v1/ips/available?subnet_id={subnet_id}&count=2")
    assert avail_res.status_code == 200
    data = avail_res.json()
    assert data["count_returned"] == 2
    assert data["available_ips"] == ["192.168.50.1", "192.168.50.2"]


def test_webhook_crud_and_test(client: TestClient):
    create_payload = {
        "name": "SIEM Integration",
        "url": "https://example.com/webhook",
        "secret": "my-shared-secret-123",
        "events": ["ip.state_changed", "scan.completed"],
    }
    res = client.post("/api/v1/webhooks", json=create_payload)
    assert res.status_code == 201
    wh_id = res.json()["id"]

    list_res = client.get("/api/v1/webhooks")
    assert len(list_res.json()) == 1

    test_res = client.post(f"/api/v1/webhooks/{wh_id}/test")
    assert test_res.status_code == 200


def test_api_key_management(client: TestClient):
    # 1. Create first key in open mode
    res = client.post("/api/v1/auth/keys", json={"name": "CI-Pipeline", "role": "operator"})
    assert res.status_code == 201
    data = res.json()
    assert "raw_key" in data
    raw_key = data["raw_key"]
    key_id = data["id"]

    # 2. Request without header should now be rejected with 401
    unauth_res = client.get("/api/v1/auth/keys")
    assert unauth_res.status_code == 401

    # 3. Request with invalid key should be rejected with 403
    forbidden_res = client.get("/api/v1/auth/keys", headers={"X-API-Key": "invalid_key"})
    assert forbidden_res.status_code == 403

    # 4. Request with valid header should succeed
    auth_headers = {"X-API-Key": raw_key}
    list_res = client.get("/api/v1/auth/keys", headers=auth_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 5. Revoke key
    del_res = client.delete(f"/api/v1/auth/keys/{key_id}", headers=auth_headers)
    assert del_res.status_code == 204
