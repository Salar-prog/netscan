from fastapi.testclient import TestClient


def test_dashboard_requires_login(client: TestClient):
    """Dashboard pages redirect to /login without a session cookie."""
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/login"


def test_login_page_renders(client: TestClient):
    res = client.get("/login")
    assert res.status_code == 200
    assert "Sign in with your API key" in res.text


def test_login_with_invalid_key(client: TestClient):
    res = client.post("/login", data={"api_key": "invalid_key"}, follow_redirects=False)
    assert res.status_code == 200
    assert "Invalid or revoked API key" in res.text


def test_login_with_valid_key(dashboard_client: TestClient):
    res = dashboard_client.get("/")
    assert res.status_code == 200
    assert "Network Subnets & IP Pools" in res.text


def test_logout_clears_session(dashboard_client: TestClient):
    # dashboard_client is already logged in — verify we can access dashboard
    res = dashboard_client.get("/")
    assert res.status_code == 200

    # Logout
    res = dashboard_client.post("/logout", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"

    # After logout, dashboard requires login again
    res = dashboard_client.get("/", follow_redirects=False)
    assert res.status_code == 307


def test_dashboard_views(dashboard_client: TestClient):
    # 1. Main Dashboard Index
    res = dashboard_client.get("/")
    assert res.status_code == 200
    assert "Network Subnets & IP Pools" in res.text

    # 2. Provision View
    prov_res = dashboard_client.get("/provision")
    assert prov_res.status_code == 200
    assert "Available IP Provisioner" in prov_res.text

    # 3. Scans View
    scans_res = dashboard_client.get("/scans")
    assert scans_res.status_code == 200
    assert "Scan Job History" in scans_res.text

    # 4. Settings View
    settings_res = dashboard_client.get("/settings")
    assert settings_res.status_code == 200
    assert "API Keys" in settings_res.text


def test_matrix_and_drawer_views(auth_client):
    client, headers = auth_client

    # Create Subnet via API
    res = client.post("/api/v1/subnets", json={"cidr": "172.16.10.0/29", "name": "Lab"}, headers=headers)
    subnet_id = res.json()["id"]

    # Matrix HTML view - requires login
    matrix_res = client.get(f"/subnets/{subnet_id}/matrix", follow_redirects=False)
    assert matrix_res.status_code == 307

    # IP Drawer for untracked IP should redirect to login
    drawer_res = client.get("/web/ips/172.16.10.1/drawer", follow_redirects=False)
    assert drawer_res.status_code == 307
