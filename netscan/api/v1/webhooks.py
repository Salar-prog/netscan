import asyncio
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlmodel import Session, select
from netscan.api.auth import get_current_api_key
from netscan.db import get_session
from netscan.models import Webhook
from netscan.services.webhook_service import WebhookDispatcher

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: str
    events: List[str] = ["ip.state_changed", "scan.completed"]
    is_active: bool = True


@router.get("", response_model=List[Webhook])
def list_webhooks(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    return session.exec(select(Webhook)).all()


@router.post("", response_model=Webhook, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    wh = Webhook(
        name=payload.name,
        url=payload.url,
        secret=payload.secret,
        events=payload.events,
        is_active=payload.is_active,
    )
    session.add(wh)
    session.commit()
    session.refresh(wh)
    return wh


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    session.delete(wh)
    session.commit()
    return None


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_data = {
        "test": True,
        "message": "NetScan test webhook delivery",
        "sample_ip": "192.168.1.100",
        "sample_status": "ACTIVE_DETECTED",
    }
    await WebhookDispatcher.dispatch_event("webhook.test", test_data, session)
    return {"message": f"Test payload dispatched to {wh.url}"}
