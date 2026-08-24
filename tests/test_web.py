from fastapi.testclient import TestClient


def test_dashboard_views(client: TestClient):
    # 1. Main Dashboard Index
    res = client.get("/")
    assert res.status_code == 200
    assert "Network Subnets & IP Pools" in res.text

    # 2. Provision View
    prov_res = client.get("/provision")
    assert prov_res.status_code == 200
    assert "Available IP Provisioner" in prov_res.text

    # 3. Scans View
    scans_res = client.get("/scans")
    assert scans_res.status_code == 200
    assert "Scan Job History" in scans_res.text

    # 4. Settings View
    settings_res = client.get("/settings")
    assert settings_res.status_code == 200
    assert "API Keys" in settings_res.text


def test_matrix_and_drawer_views(auth_client):
    client, headers = auth_client

    # Create Subnet via API
    res = client.post("/api/v1/subnets", json={"cidr": "172.16.10.0/29", "name": "Lab"}, headers=headers)
    subnet_id = res.json()["id"]

    # Matrix HTML view
    matrix_res = client.get(f"/subnets/{subnet_id}/matrix")
    assert matrix_res.status_code == 200
    assert "172.16.10.0/29" in matrix_res.text

    # IP Drawer for untracked IP should return 404 (no phantom IPs)
    drawer_res = client.get("/web/ips/172.16.10.1/drawer")
    assert drawer_res.status_code == 404
