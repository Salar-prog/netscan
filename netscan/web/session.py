import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import quote, unquote

from netscan.api.auth import hash_key
from netscan.config import settings

COOKIE_NAME = "netscan_session"
COOKIE_MAX_AGE = 86400 * 7  # 7 days


def _sign(payload: str) -> str:
    secret = settings.SESSION_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_cookie(raw_api_key: str) -> str:
    """Create a signed session cookie from an API key. Format: ak:{key_hash}:{ts}:{sig}"""
    key_hash = hash_key(raw_api_key)
    payload = f"ak:{key_hash}:{int(time.time())}"
    sig = _sign(payload)
    return quote(f"{payload}:{sig}")


def create_ldap_session_cookie(username: str, role: str) -> str:
    """Create a signed session cookie for LDAP auth. Format: ldap:{username}:{role}:{ts}:{sig}"""
    payload = f"ldap:{username}:{role}:{int(time.time())}"
    sig = _sign(payload)
    return quote(f"{payload}:{sig}")


def validate_session_cookie(cookie_value: str) -> Optional[Dict[str, Any]]:
    """Validate a session cookie and return auth info, or None if invalid.

    Returns:
        {"type": "ak", "key_hash": "..."} for API key sessions
        {"type": "ldap", "username": "...", "role": "..."} for LDAP sessions
    """
    try:
        decoded = unquote(cookie_value)
        parts = decoded.split(":")
        if len(parts) < 3:
            return None

        cookie_type = parts[0]

        if cookie_type == "ak" and len(parts) == 4:
            _, key_hash, created_at_str, sig = parts
            payload = f"ak:{key_hash}:{created_at_str}"
            expected_sig = _sign(payload)
            if not hmac.compare_digest(sig, expected_sig):
                return None
            if time.time() - int(created_at_str) > COOKIE_MAX_AGE:
                return None
            return {"type": "ak", "key_hash": key_hash}

        if cookie_type == "ldap" and len(parts) == 5:
            _, username, role, created_at_str, sig = parts
            payload = f"ldap:{username}:{role}:{created_at_str}"
            expected_sig = _sign(payload)
            if not hmac.compare_digest(sig, expected_sig):
                return None
            if time.time() - int(created_at_str) > COOKIE_MAX_AGE:
                return None
            return {"type": "ldap", "username": username, "role": role}

        return None
    except (ValueError, TypeError):
        return None
