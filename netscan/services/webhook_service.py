import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import httpx
from sqlmodel import Session, select
from netscan.config import settings
from netscan.models import Webhook

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Dispatches webhook events with full object snapshots and HMAC signatures."""

    @staticmethod
    def generate_signature(secret: str, payload_bytes: bytes) -> str:
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    async def dispatch_event(
        cls,
        event_name: str,
        data: Dict[str, Any],
        session: Session,
    ) -> None:
        statement = select(Webhook).where(Webhook.is_active == True)
        webhooks = session.exec(statement).all()

        if not webhooks:
            return

        payload = {
            "event": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        payload_json = json.dumps(payload, default=str)
        payload_bytes = payload_json.encode("utf-8")

        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            for wh in webhooks:
                # Check if webhook is subscribed to this event
                if wh.events and event_name not in wh.events and "*" not in wh.events:
                    continue

                signature = cls.generate_signature(wh.secret, payload_bytes)
                headers = {
                    "Content-Type": "application/json",
                    "X-NetScan-Event": event_name,
                    "X-NetScan-Signature": signature,
                }

                for attempt in range(settings.WEBHOOK_MAX_RETRIES):
                    try:
                        response = await client.post(wh.url, content=payload_bytes, headers=headers)
                        if response.is_success:
                            logger.info(f"Webhook '{wh.name}' delivered successfully for event {event_name}")
                            break
                        else:
                            logger.warning(f"Webhook '{wh.name}' returned status {response.status_code} on attempt {attempt + 1}")
                    except Exception as e:
                        logger.error(f"Webhook '{wh.name}' delivery error on attempt {attempt + 1}: {e}")
