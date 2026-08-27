import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel import Session, select

from netscan.db import engine
from netscan.models import IdempotencyRecord

_IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_TTL_SECONDS = 86400  # 24 hours


def _hash_request(method: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(f"{method}:{path}:".encode())
    h.update(body)
    return h.hexdigest()


class IdempotencyKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get("idempotency-key")
        if not idempotency_key or request.method not in _IDEMPOTENT_METHODS:
            return await call_next(request)

        body = await request.body()
        req_hash = _hash_request(request.method, request.url.path, body)
        endpoint = f"{request.method} {request.url.path}"

        with Session(engine) as session:
            # Prune expired records
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=_TTL_SECONDS)
            expired = session.exec(select(IdempotencyRecord).where(IdempotencyRecord.created_at < cutoff)).all()
            for rec in expired:
                session.delete(rec)
            if expired:
                session.commit()

            existing = session.exec(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == idempotency_key)
            ).first()

            if existing:
                if existing.endpoint == endpoint and existing.request_hash == req_hash:
                    return Response(
                        content=json.dumps(existing.response_body, default=str),
                        status_code=existing.status_code,
                        media_type="application/json",
                    )
                # Different request with same key — conflict
                return Response(
                    content=json.dumps(
                        {"error_code": "IDEMPOTENCY_CONFLICT", "message": "Key reused with different request body."}
                    ),
                    status_code=409,
                    media_type="application/json",
                )

        # No existing record — process the request
        response = await call_next(request)

        # Store the result (only for successful/expected responses, not 500s)
        if response.status_code < 500:
            resp_body = b""
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    resp_body += chunk.encode()
                else:
                    resp_body += chunk

            try:
                resp_json = json.loads(resp_body)
            except (json.JSONDecodeError, ValueError):
                resp_json = {}

            with Session(engine) as session:
                record = IdempotencyRecord(
                    idempotency_key=idempotency_key,
                    endpoint=endpoint,
                    request_hash=req_hash,
                    status_code=response.status_code,
                    response_body=resp_json,
                )
                session.add(record)
                session.commit()

            return Response(
                content=resp_body,
                status_code=response.status_code,
                media_type="application/json",
                headers=dict(response.headers),
            )

        return response
