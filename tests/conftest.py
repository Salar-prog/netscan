import os
os.environ.setdefault("DEBUG", "true")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool
from netscan.db import get_session
from netscan.main import app
from netscan.models import Role


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


@pytest.fixture(name="auth_client")
def auth_client_fixture():
    """Client with a bootstrapped API key for authenticated API tests."""
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
        # Bootstrap first API key
        res = client.post("/api/v1/auth/keys/bootstrap", json={"name": "test-key"})
        raw_key = res.json()["raw_key"]
        yield client, {"X-API-Key": raw_key}
    app.dependency_overrides.clear()


@pytest.fixture(name="make_key_headers")
def make_key_headers_fixture(auth_client):
    """Factory fixture: returns (client, make_headers) where make_headers(role)
    creates an API key with the given role and returns auth headers for it."""
    client, admin_headers = auth_client

    def _make(role: Role) -> dict:
        res = client.post(
            "/api/v1/auth/keys",
            json={"name": f"{role.value}-key", "role": role.value},
            headers=admin_headers,
        )
        assert res.status_code == 201, res.text
        return {"X-API-Key": res.json()["raw_key"]}

    return client, _make


@pytest.fixture(name="auth_db")
def auth_db_fixture():
    """Like auth_client but also yields the underlying engine for direct DB seeding."""
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
        res = client.post("/api/v1/auth/keys/bootstrap", json={"name": "test-key"})
        raw_key = res.json()["raw_key"]
        yield client, {"X-API-Key": raw_key}, engine
    app.dependency_overrides.clear()
