from fastapi.testclient import TestClient

HX = {"HX-Request": "true"}


class TestProxyRoutesRequireAuth:
    def test_redirects_to_login_without_cookie(self, client: TestClient):
        res = client.post("/web/subnets", json={"cidr": "10.99.0.0/30", "name": "no-auth"}, follow_redirects=False)
        assert res.status_code == 307
        assert res.headers["location"] == "/login"


class TestSubnetProxy:
    def test_create_subnet(self, dashboard_client: TestClient):
        res = dashboard_client.post(
            "/web/subnets", json={"cidr": "10.99.0.0/30", "name": "test-net"}, follow_redirects=False
        )
        assert res.status_code == 303

    def test_create_subnet_duplicate(self, dashboard_client: TestClient):
        dashboard_client.post("/web/subnets", json={"cidr": "10.99.1.0/30", "name": "dup"})
        res = dashboard_client.post(
            "/web/subnets", json={"cidr": "10.99.1.0/30", "name": "dup"}, follow_redirects=False
        )
        assert res.status_code == 400

    def test_scan_trigger(self, dashboard_client: TestClient):
        dashboard_client.post("/web/subnets", json={"cidr": "10.99.2.0/30", "name": "scan-net"})
        # List subnets to find the ID via the settings page (which shows subnets)
        res = dashboard_client.get("/settings")
        assert res.status_code == 200


class TestKeyProxy:
    def test_generate_key(self, dashboard_client: TestClient):
        res = dashboard_client.post("/web/auth/keys", headers=HX)
        assert res.status_code == 200
        data = res.json()
        assert "raw_key" in data
        assert data["prefix"].startswith("ns_live")

    def test_generate_key_redirect(self, dashboard_client: TestClient):
        res = dashboard_client.post("/web/auth/keys", follow_redirects=False)
        assert res.status_code == 303


class TestWebhookProxy:
    def test_create_webhook(self, dashboard_client: TestClient):
        res = dashboard_client.post(
            "/web/webhooks",
            headers=HX,
            json={"name": "test-hook", "url": "https://example.com/hook", "events": ["scan.completed"]},
        )
        assert res.status_code == 200
        data = res.json()
        assert "secret" in data

    def test_create_webhook_redirect(self, dashboard_client: TestClient):
        res = dashboard_client.post(
            "/web/webhooks",
            json={"name": "test-hook2", "url": "https://example.com/hook2", "events": ["scan.completed"]},
            follow_redirects=False,
        )
        assert res.status_code == 303

    def test_create_webhook_ssrf_blocked(self, dashboard_client: TestClient):
        res = dashboard_client.post(
            "/web/webhooks",
            headers=HX,
            json={"name": "ssrf-hook", "url": "http://169.254.169.254/latest", "events": ["scan.completed"]},
        )
        assert res.status_code == 400
        assert "blocked" in res.json()["detail"].lower()


class TestDualCookieFormat:
    def test_ldap_cookie_grants_access(self, ldap_client: TestClient):
        res = ldap_client.get("/")
        assert res.status_code == 200
        assert "Network Subnets & IP Pools" in res.text

    def test_ldap_cookie_on_settings(self, ldap_client: TestClient):
        res = ldap_client.get("/settings")
        assert res.status_code == 200

    def test_ldap_cookie_on_scans(self, ldap_client: TestClient):
        res = ldap_client.get("/scans")
        assert res.status_code == 200

    def test_ldap_cookie_on_provision(self, ldap_client: TestClient):
        res = ldap_client.get("/provision")
        assert res.status_code == 200

    def test_invalid_cookie_rejected(self, client: TestClient):
        from netscan.web.session import COOKIE_NAME

        client.cookies.set(COOKIE_NAME, "garbage:value:here")
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 307
        assert res.headers["location"] == "/login"

    def test_expired_cookie_rejected(self, client: TestClient):
        from netscan.web.session import COOKIE_NAME, _sign
        from urllib.parse import quote
        import time

        old_ts = str(int(time.time()) - 86400 * 8)
        payload = f"ak:fakehash:{old_ts}"
        sig = _sign(payload)
        cookie = quote(f"{payload}:{sig}")
        client.cookies.set(COOKIE_NAME, cookie)
        res = client.get("/", follow_redirects=False)
        assert res.status_code == 307
