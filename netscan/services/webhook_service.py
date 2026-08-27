import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
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
        statement = select(Webhook).where(Webhook.is_active)
        webhooks = session.exec(statement).all()

        if not webhooks:
            return

        payload = {
            "event": event_name,
            "event_id": str(uuid.uuid4()),
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
                    attempt_start = time.monotonic()
                    try:
                        response = await client.post(wh.url, content=payload_bytes, headers=headers)
                        duration_ms = int((time.monotonic() - attempt_start) * 1000)
                        if response.is_success:
                            logger.info(
                                "Webhook delivered",
                                extra={
                                    "extra_data": {
                                        "webhook_name": wh.name,
                                        "event": event_name,
                                        "status_code": response.status_code,
                                        "duration_ms": duration_ms,
                                    }
                                },
                            )
                            break
                        else:
                            logger.warning(
                                "Webhook returned error",
                                extra={
                                    "extra_data": {
                                        "webhook_name": wh.name,
                                        "event": event_name,
                                        "status_code": response.status_code,
                                        "attempt": attempt + 1,
                                        "duration_ms": duration_ms,
                                    }
                                },
                            )
                    except Exception as e:
                        duration_ms = int((time.monotonic() - attempt_start) * 1000)
                        logger.error(
                            "Webhook delivery failed",
                            extra={
                                "extra_data": {
                                    "webhook_name": wh.name,
                                    "event": event_name,
                                    "error": str(e),
                                    "attempt": attempt + 1,
                                    "duration_ms": duration_ms,
                                }
                            },
                        )

                    if attempt < settings.WEBHOOK_MAX_RETRIES - 1:
                        await asyncio.sleep(min(2**attempt, 30))

    @classmethod
    async def dispatch_event_to(
        cls,
        event_name: str,
        data: Dict[str, Any],
        webhook: Webhook,
        session: Session,
    ) -> None:
        """Dispatch an event to a specific webhook (for test deliveries)."""
        payload = {
            "event": event_name,
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        payload_json = json.dumps(payload, default=str)
        payload_bytes = payload_json.encode("utf-8")

        signature = cls.generate_signature(webhook.secret, payload_bytes)
        headers = {
            "Content-Type": "application/json",
            "X-NetScan-Event": event_name,
            "X-NetScan-Signature": signature,
        }

        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            for attempt in range(settings.WEBHOOK_MAX_RETRIES):
                attempt_start = time.monotonic()
                try:
                    response = await client.post(webhook.url, content=payload_bytes, headers=headers)
                    duration_ms = int((time.monotonic() - attempt_start) * 1000)
                    if response.is_success:
                        logger.info(
                            "Webhook delivered",
                            extra={
                                "extra_data": {
                                    "webhook_name": webhook.name,
                                    "event": event_name,
                                    "status_code": response.status_code,
                                    "duration_ms": duration_ms,
                                }
                            },
                        )
                        break
                    else:
                        logger.warning(
                            "Webhook returned error",
                            extra={
                                "extra_data": {
                                    "webhook_name": webhook.name,
                                    "event": event_name,
                                    "status_code": response.status_code,
                                    "attempt": attempt + 1,
                                    "duration_ms": duration_ms,
                                }
                            },
                        )
                except Exception as e:
                    duration_ms = int((time.monotonic() - attempt_start) * 1000)
                    logger.error(
                        "Webhook delivery failed",
                        extra={
                            "extra_data": {
                                "webhook_name": webhook.name,
                                "event": event_name,
                                "error": str(e),
                                "attempt": attempt + 1,
                                "duration_ms": duration_ms,
                            }
                        },
                    )

                if attempt < settings.WEBHOOK_MAX_RETRIES - 1:
                    await asyncio.sleep(min(2**attempt, 30))
