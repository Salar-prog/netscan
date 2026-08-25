from fastapi.testclient import TestClient
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


def seed_ip(engine, subnet_id, ip, status=IPStatus.AVAILABLE_CANDIDATE, **kwargs):
    from sqlmodel import Session
    from netscan.models import IPAddress

    with Session(engine) as session:
        rec = IPAddress(subnet_id=subnet_id, ip=ip, status=status, **kwargs)
        session.add(rec)
        session.commit()
        session.refresh(rec)
        return rec.id


def seed_subnet(engine, cidr="192.168.77.0/29"):
    import uuid
    from sqlmodel import Session
    from netscan.models import Subnet

    with Session(engine) as session:
        subnet = Subnet(id=uuid.uuid4(), cidr=cidr, name="Seeded")
        session.add(subnet)
        session.commit()
        return subnet.id


def test_patch_ip_reserve_and_history(auth_db):
    client, headers, engine = auth_db
    subnet_id = seed_subnet(engine)
    seed_ip(engine, subnet_id, "192.168.77.10")

    patch = {"is_reserved": True, "hostname": "printer.corp", "custom_metadata": {"owner": "infra-team"}}
    res = client.patch("/api/v1/ips/192.168.77.10", json=patch, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == IPStatus.ASSIGNED_RESERVED.value
    assert data["custom_metadata"] == {"owner": "infra-team"}

    history = client.get("/api/v1/ips/192.168.77.10/history", headers=headers).json()
    assert history["current_status"] == IPStatus.ASSIGNED_RESERVED.value
    assert len(history["timeline"]) == 1
    entry = history["timeline"][0]
    assert entry["event_type"] == "RESERVED_TOGGLE"
    assert entry["old_status"] == IPStatus.AVAILABLE_CANDIDATE.value
    assert entry["new_status"] == IPStatus.ASSIGNED_RESERVED.value


def test_patch_ip_unreserve_releases_to_available(auth_db):
    client, headers, engine = auth_db
    subnet_id = seed_subnet(engine)
    seed_ip(engine, subnet_id, "192.168.77.11", status=IPStatus.ASSIGNED_RESERVED)

    res = client.patch("/api/v1/ips/192.168.77.11", json={"is_reserved": False}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == IPStatus.AVAILABLE_CANDIDATE.value

    history = client.get("/api/v1/ips/192.168.77.11/history", headers=headers).json()
    assert len(history["timeline"]) == 1
    assert history["timeline"][0]["old_status"] == IPStatus.ASSIGNED_RESERVED.value


def test_patch_metadata_only_keeps_status(auth_db):
    client, headers, engine = auth_db
    subnet_id = seed_subnet(engine)
    seed_ip(engine, subnet_id, "192.168.77.12", status=IPStatus.ACTIVE_DETECTED)

    res = client.patch(
        "/api/v1/ips/192.168.77.12",
        json={"is_reserved": False, "custom_metadata": {"note": "checked"}},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == IPStatus.ACTIVE_DETECTED.value
    assert data["custom_metadata"] == {"note": "checked"}

    history = client.get("/api/v1/ips/192.168.77.12/history", headers=headers).json()
    assert len(history["timeline"]) == 0


def test_patch_unknown_ip_returns_404(auth_client):
    client, headers = auth_client
    res = client.patch("/api/v1/ips/203.0.113.99", json={"is_reserved": True}, headers=headers)
    assert res.status_code == 404


def test_scan_concurrency_guard(auth_db):
    client, headers, engine = auth_db

    res = client.post("/api/v1/subnets", json={"cidr": "10.20.0.0/30", "name": "Concurrency Test"}, headers=headers)
    subnet_id = res.json()["id"]

    # Create an active scan job directly in the DB
    import uuid
    from sqlmodel import Session
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
    dup_scan = client.post(f"/api/v1/subnets/{subnet_id}/scan", headers=headers)
    assert dup_scan.status_code == 409
    assert "already in progress" in dup_scan.json()["detail"]


def test_get_ip_detail_and_404(auth_db):
    client, headers, engine = auth_db
    subnet_id = seed_subnet(engine)
    seed_ip(engine, subnet_id, "192.168.77.13", hostname="nas.local")

    res = client.get("/api/v1/ips/192.168.77.13", headers=headers)
    assert res.status_code == 200
    assert res.json()["hostname"] == "nas.local"

    missing = client.get("/api/v1/ips/203.0.113.98", headers=headers)
    assert missing.status_code == 404

    missing_history = client.get("/api/v1/ips/203.0.113.98/history", headers=headers)
    assert missing_history.status_code == 404


def test_webhook_ssrf_blocklist(auth_client):
    client, headers = auth_client

    blocked_urls = [
        "http://127.0.0.1:8080/hook",
        "http://10.0.0.1/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://172.16.0.1/hook",
    ]

    for url in blocked_urls:
        res = client.post("/api/v1/webhooks", json={"name": "test", "url": url}, headers=headers)
        assert res.status_code == 400, f"Expected 400 for {url}"
        assert "private/internal" in res.json()["detail"]

    # Public URL should work
    res = client.post("/api/v1/webhooks", json={"name": "ok", "url": "https://example.com/hook"}, headers=headers)
    assert res.status_code == 201
