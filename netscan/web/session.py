import hashlib
import hmac
import time
from urllib.parse import quote, unquote

from netscan.api.auth import hash_key
from netscan.config import settings

COOKIE_NAME = "netscan_session"
COOKIE_MAX_AGE = 86400 * 7  # 7 days


def _sign(payload: str) -> str:
    secret = settings.SESSION_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_cookie(raw_api_key: str) -> str:
    """Create a signed session cookie from an API key."""
    key_hash = hash_key(raw_api_key)
    payload = f"{key_hash}:{int(time.time())}"
    sig = _sign(payload)
    return quote(f"{payload}:{sig}")


def validate_session_cookie(cookie_value: str) -> str | None:
    """Validate a session cookie and return the key_hash, or None if invalid."""
    try:
        decoded = unquote(cookie_value)
        parts = decoded.split(":")
        if len(parts) != 3:
            return None
        key_hash, created_at_str, sig = parts
        payload = f"{key_hash}:{created_at_str}"
        expected_sig = _sign(payload)
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if time.time() - int(created_at_str) > COOKIE_MAX_AGE:
            return None
        return key_hash
    except (ValueError, TypeError):
        return None
