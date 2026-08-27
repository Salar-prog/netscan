import secrets
import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from pydantic import AnyHttpUrl, BaseModel
from sqlmodel import Session, select
from netscan.api.auth import get_current_api_key, require_role
from netscan.api.errors import NetScanException
from netscan.db import get_session
from netscan.models import Role, Webhook
from netscan.services.webhook_service import WebhookDispatcher
from netscan.webhooks_check import is_url_blocked

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    name: str
    url: AnyHttpUrl
    events: List[str] = ["ip.state_changed", "scan.completed"]
    is_active: bool = True


class WebhookResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    events: List[str]
    is_active: bool
    created_at: str


@router.get("", response_model=List[WebhookResponse])
def list_webhooks(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    webhooks = session.exec(select(Webhook)).all()
    return [
        WebhookResponse(
            id=wh.id,
            name=wh.name,
            url=wh.url,
            events=wh.events,
            is_active=wh.is_active,
            created_at=str(wh.created_at),
        )
        for wh in webhooks
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    if is_url_blocked(str(payload.url)):
        raise NetScanException(
            "SSRF_BLOCKED",
            "Webhook URL points to a private/internal IP range. Use a public URL.",
            status_code=400,
        )

    raw_secret = secrets.token_urlsafe(32)
    wh = Webhook(
        name=payload.name,
        url=str(payload.url),
        secret=raw_secret,
        events=payload.events,
        is_active=payload.is_active,
    )
    session.add(wh)
    session.commit()
    session.refresh(wh)
    return {
        "id": wh.id,
        "name": wh.name,
        "url": wh.url,
        "secret": raw_secret,
        "events": wh.events,
        "is_active": wh.is_active,
        "created_at": wh.created_at,
        "message": "Store this secret safely! It will never be shown again.",
    }


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise NetScanException("WEBHOOK_NOT_FOUND", "Webhook not found", status_code=404)
    session.delete(wh)
    session.commit()
    return None


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN, Role.OPERATOR)),
):
    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise NetScanException("WEBHOOK_NOT_FOUND", "Webhook not found", status_code=404)

    test_data = {
        "test": True,
        "message": "NetScan test webhook delivery",
        "sample_ip": "192.168.1.100",
        "sample_status": "ACTIVE_DETECTED",
    }
    await WebhookDispatcher.dispatch_event_to("webhook.test", test_data, wh, session)
    return {"message": f"Test payload dispatched to {wh.url}"}
