from click.testing import CliRunner
from fastapi.testclient import TestClient
from netscan.cli import main
from netscan.main import create_app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "NetScan" in result.output


def test_serve_help():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--dashboard" in result.output
    assert "--no-dashboard" in result.output


def test_create_app_default_has_web_routes():
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/")
    assert resp.status_code == 200


def test_create_app_dashboard_true_has_web_routes():
    app = create_app(dashboard=True)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/")
    assert resp.status_code == 200


def test_create_app_dashboard_false_no_web_routes():
    app = create_app(dashboard=False)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/")
    assert resp.status_code == 404


def test_create_app_always_has_api_routes():
    app = create_app(dashboard=False)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_create_app_always_has_health():
    app = create_app(dashboard=False)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "NetScan"
