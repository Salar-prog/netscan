from netscan.models import Role


def test_read_only_can_access_reads_but_not_writes(make_key_headers):
    client, make_headers = make_key_headers
    headers = make_headers(Role.READ_ONLY)

    assert client.get("/api/v1/subnets", headers=headers).status_code == 200
    assert client.get("/api/v1/scans", headers=headers).status_code == 200
    assert client.get("/api/v1/webhooks", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/keys", headers=headers).status_code == 200

    create_res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.0.0.0/29", "name": "RO Attempt"},
        headers=headers,
    )
    assert create_res.status_code == 403

    key_create_res = client.post("/api/v1/auth/keys", json={"name": "RO Key"}, headers=headers)
    assert key_create_res.status_code == 403


def test_operator_can_write_subnets_and_ips_but_not_manage_keys(make_key_headers):
    client, make_headers = make_key_headers
    operator = make_headers(Role.OPERATOR)

    res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.20.0.0/30", "name": "Op Pool"},
        headers=operator,
    )
    assert res.status_code == 201
    subnet_id = res.json()["id"]

    scan_res = client.post(f"/api/v1/subnets/{subnet_id}/scan", headers=operator)
    assert scan_res.status_code == 200

    ip_res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.20.0.4/30", "name": "Op Pool 2"},
        headers=operator,
    )
    assert ip_res.status_code == 201

    key_create_res = client.post("/api/v1/auth/keys", json={"name": "Op Key"}, headers=operator)
    assert key_create_res.status_code == 403

    keys_list = client.get("/api/v1/auth/keys", headers=operator).json()
    revoke_res = client.delete(f"/api/v1/auth/keys/{keys_list[0]['id']}", headers=operator)
    assert revoke_res.status_code == 403


def test_admin_can_manage_keys_and_writes(make_key_headers):
    client, make_headers = make_key_headers
    admin = make_headers(Role.ADMIN)

    res = client.post(
        "/api/v1/auth/keys",
        json={"name": "Admin Created", "role": Role.READ_ONLY.value},
        headers=admin,
    )
    assert res.status_code == 201
    new_key_id = res.json()["id"]

    del_res = client.delete(f"/api/v1/auth/keys/{new_key_id}", headers=admin)
    assert del_res.status_code == 204

    subnet_res = client.post(
        "/api/v1/subnets",
        json={"cidr": "10.30.0.0/30", "name": "Admin Pool"},
        headers=admin,
    )
    assert subnet_res.status_code == 201


def test_revoked_key_is_rejected(make_key_headers):
    client, make_headers = make_key_headers
    admin = make_headers(Role.ADMIN)

    res = client.post("/api/v1/auth/keys", json={"name": "Shortlived"}, headers=admin)
    raw_key = res.json()["raw_key"]
    key_id = res.json()["id"]
    temp_headers = {"X-API-Key": raw_key}

    assert client.get("/api/v1/subnets", headers=temp_headers).status_code == 200

    revoke = client.delete(f"/api/v1/auth/keys/{key_id}", headers=admin)
    assert revoke.status_code == 204

    assert client.get("/api/v1/subnets", headers=temp_headers).status_code == 403


def test_list_keys_does_not_expose_key_hash(make_key_headers):
    client, _ = make_key_headers

    res = client.get("/api/v1/auth/keys")
    assert res.status_code == 401

    client2, make_headers = make_key_headers
    admin = make_headers(Role.ADMIN)

    keys = client2.get("/api/v1/auth/keys", headers=admin).json()
    assert len(keys) >= 1
    for key in keys:
        assert "key_hash" not in key
    assert set(keys[0].keys()) == {
        "id",
        "name",
        "prefix",
        "role",
        "is_active",
        "last_used_at",
        "created_at",
    }
