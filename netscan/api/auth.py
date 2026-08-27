import hashlib
import secrets
from datetime import timezone
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlmodel import Session, select
from netscan.db import get_session
from netscan.models import ApiKey, Role, utc_now


def require_role(*allowed: Role):
    """Dependency factory enforcing that the authenticated key has one of the allowed roles."""

    async def checker(current_user: ApiKey = Depends(get_current_api_key)) -> ApiKey:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Requires one of: {', '.join(r.value for r in allowed)}.",
            )
        return current_user

    return checker


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key(prefix: str = "ns_live") -> tuple[str, str, str]:
    """Generate (raw_key, key_hash, prefix)."""
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{prefix}_{random_part}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return raw_key, key_hash, raw_key[:12]


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


async def get_current_api_key(
    header_key: Optional[str] = Security(api_key_header),
    session: Session = Depends(get_session),
) -> Optional[ApiKey]:
    """Validate API key. No keys in DB = no access (create first key via CLI or direct DB)."""
    if not header_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required via X-API-Key header.",
        )

    hashed = hash_key(header_key)
    key_rec = session.exec(select(ApiKey).where(ApiKey.key_hash == hashed, ApiKey.is_active)).first()

    if not key_rec:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API Key.",
        )

    if key_rec.expires_at and key_rec.expires_at.replace(tzinfo=timezone.utc) < utc_now():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key has expired.",
        )

    now = utc_now()
    if not key_rec.last_used_at or (now - key_rec.last_used_at.replace(tzinfo=timezone.utc)).total_seconds() > 3600:
        key_rec.last_used_at = now
        session.add(key_rec)
        session.commit()
    return key_rec
