import pytest
from fastapi.testclient import TestClient
from netscan.main import app
from netscan.models import IPStatus


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "NetScan"
    assert "checks" in data


def test_subnet_crud_and_matrix(auth_client):
    client, headers = auth_client

    create_payload = {
        "cidr": "10.10.0.0/29",
        "name": "Dev Lab Pool",
        "scan_interval_minutes": 30,
        "miss_threshold": 2,
        "quarantine_hours": 24,
    }
    res = client.post("/api/v1/subnets", json=create_payload, headers=headers)
    assert res.status_code == 201
    subnet_data = res.json()
    subnet_id = subnet_data["id"]
    assert subnet_data["cidr"] == "10.10.0.0/29"

    # Duplicate rejection
    dup_res = client.post("/api/v1/subnets", json=create_payload, headers=headers)
    assert dup_res.status_code == 400

    # List Subnets
    list_res = client.get("/api/v1/subnets", headers=headers)
    assert list_res.status_code == 200
    subnets = list_res.json()
    assert len(subnets) == 1
    assert subnets[0]["stats"]["total"] == 6

    # Get Matrix
    matrix_res = client.get(f"/api/v1/subnets/{subnet_id}/matrix", headers=headers)
    assert matrix_res.status_code == 200
    matrix_data = matrix_res.json()
    assert matrix_data["total_hosts"] == 6
    assert len(matrix_data["matrix"]) == 6
    assert matrix_data["matrix"][0]["status"] == "AVAILABLE_CANDIDATE"


def test_available_ips_query(auth_client):
    client, headers = auth_client

    res = client.post("/api/v1/subnets", json={"cidr": "192.168.50.0/30", "name": "Point to Point"}, headers=headers)
    subnet_id = res.json()["id"]

    avail_res = client.get(f"/api/v1/ips/available?subnet_id={subnet_id}&count=2", headers=headers)
    assert avail_res.status_code == 200
    data = avail_res.json()
    assert data["count_returned"] == 2
    assert data["available_ips"] == ["192.168.50.1", "192.168.50.2"]


def test_webhook_crud_and_test(auth_client):
    client, headers = auth_client

    create_payload = {
        "name": "SIEM Integration",
        "url": "https://example.com/webhook",
        "events": ["ip.state_changed", "scan.completed"],
    }
    res = client.post("/api/v1/webhooks", json=create_payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    wh_id = data["id"]
    assert "secret" in data
    assert "message" in data
    assert len(data["secret"]) > 10

    list_res = client.get("/api/v1/webhooks", headers=headers)
    assert len(list_res.json()) == 1

    test_res = client.post(f"/api/v1/webhooks/{wh_id}/test", headers=headers)
    assert test_res.status_code == 200


def test_api_key_management(auth_client):
    client, headers = auth_client

    # 1. List should show the bootstrap key
    list_res = client.get("/api/v1/auth/keys", headers=headers)
    assert list_res.status_code == 200
    keys = list_res.json()
    assert len(keys) == 1
    key_id = keys[0]["id"]

    # 2. Request without header should be rejected with 401
    unauth_res = client.get("/api/v1/auth/keys")
    assert unauth_res.status_code == 401

    # 3. Request with invalid key should be rejected with 403
    forbidden_res = client.get("/api/v1/auth/keys", headers={"X-API-Key": "invalid_key"})
    assert forbidden_res.status_code == 403

    # 4. Create a second key
    create_res = client.post("/api/v1/auth/keys", json={"name": "Second Key"}, headers=headers)
    assert create_res.status_code == 201

    # 5. Revoke first key
    del_res = client.delete(f"/api/v1/auth/keys/{key_id}", headers=headers)
    assert del_res.status_code == 204
