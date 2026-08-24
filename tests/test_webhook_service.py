import hashlib
import hmac
import json
import sys
import uuid

import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool
from netscan.models import Webhook
from netscan.services.webhook_service import WebhookDispatcher

webhook_module = sys.modules["netscan.services.webhook_service"]


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    @property
    def is_success(self):
        return 200 <= self.status_code < 300


class FakeAsyncClient:
    """Records POSTs and replays scripted status codes per URL."""

    calls = []
    script = {}

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, content=None, headers=None):
        FakeAsyncClient.calls.append({"url": url, "content": content, "headers": headers})
        statuses = self.script.setdefault(url, [200])
        status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
        return FakeResponse(status)


@pytest.fixture(name="db_engine")
def db_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="patch_client")
def patch_client_fixture(monkeypatch):
    FakeAsyncClient.calls = []
    monkeypatch.setattr(webhook_module.httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def add_webhook(db_engine, name, url, events, is_active=True):
    with Session(db_engine) as session:
        wh = Webhook(
            id=uuid.uuid4(),
            name=name,
            url=url,
            secret="test-secret",
            events=events,
            is_active=is_active,
        )
        session.add(wh)
        session.commit()
        return wh.id


def test_generate_signature_matches_hmac_sha256():
    expected = hmac.new(b"secret", b"payload", hashlib.sha256).hexdigest()
    assert WebhookDispatcher.generate_signature("secret", b"payload") == expected


async def test_dispatch_with_no_webhooks_makes_no_requests(db_engine, patch_client):
    with Session(db_engine) as session:
        await WebhookDispatcher.dispatch_event("ip.state_changed", {"ip": "1.2.3.4"}, session)
    assert patch_client.calls == []


async def test_dispatch_respects_event_subscription_and_wildcard(db_engine, patch_client):
    add_webhook(db_engine, "scoped", "https://a.example.com/hook", ["scan.completed"])
    add_webhook(db_engine, "wildcard", "https://b.example.com/hook", ["*"])
    add_webhook(db_engine, "inactive", "https://c.example.com/hook", ["*"], is_active=False)

    with Session(db_engine) as session:
        await WebhookDispatcher.dispatch_event("ip.state_changed", {"ip": "1.2.3.4"}, session)

    urls = [call["url"] for call in patch_client.calls]
    assert urls == ["https://b.example.com/hook"]


async def test_dispatch_sends_signed_snapshot_payload(db_engine, patch_client):
    add_webhook(db_engine, "all", "https://a.example.com/hook", [])

    data = {"ip": "10.0.0.1", "new_status": "ACTIVE_DETECTED"}
    with Session(db_engine) as session:
        await WebhookDispatcher.dispatch_event("ip.state_changed", data, session)

    assert len(patch_client.calls) == 1
    call = patch_client.calls[0]
    payload = json.loads(call["content"])
    assert payload["event"] == "ip.state_changed"
    assert payload["data"] == data
    assert "timestamp" in payload

    expected_sig = hmac.new(b"test-secret", call["content"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-NetScan-Signature"] == expected_sig
    assert call["headers"]["X-NetScan-Event"] == "ip.state_changed"


async def test_dispatch_retries_until_success(db_engine, patch_client, monkeypatch):
    from netscan.config import settings

    monkeypatch.setattr(settings, "WEBHOOK_MAX_RETRIES", 4)
    add_webhook(
        db_engine,
        "flaky",
        "https://flaky.example.com/hook",
        [],
    )
    patch_client.script = {"https://flaky.example.com/hook": [500, 503, 200]}

    with Session(db_engine) as session:
        await WebhookDispatcher.dispatch_event("ip.state_changed", {}, session)

    assert len(patch_client.calls) == 3


async def test_dispatch_gives_up_after_max_retries(db_engine, patch_client, monkeypatch):
    from netscan.config import settings

    monkeypatch.setattr(settings, "WEBHOOK_MAX_RETRIES", 3)
    add_webhook(db_engine, "dead", "https://dead.example.com/hook", [])
    patch_client.script = {"https://dead.example.com/hook": [500]}

    with Session(db_engine) as session:
        await WebhookDispatcher.dispatch_event("ip.state_changed", {}, session)

    assert len(patch_client.calls) == 3
