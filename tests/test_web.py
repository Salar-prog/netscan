import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from netscan.db import get_session
from netscan.main import app
from netscan.models import Subnet


@pytest.fixture(name="client")
def client_fixture():
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


def test_matrix_and_drawer_views(client: TestClient):
    # Create Subnet via API
    res = client.post("/api/v1/subnets", json={"cidr": "172.16.10.0/29", "name": "Lab"})
    subnet_id = res.json()["id"]

    # Matrix HTML view
    matrix_res = client.get(f"/subnets/{subnet_id}/matrix")
    assert matrix_res.status_code == 200
    assert "172.16.10.0/29" in matrix_res.text

    # IP Drawer Partial HTML
    drawer_res = client.get("/web/ips/172.16.10.1/drawer")
    assert drawer_res.status_code == 200
    assert "172.16.10.1" in drawer_res.text
