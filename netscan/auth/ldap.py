import asyncio
import logging
from typing import Any, Dict, List, Optional

from netscan.config import settings
from netscan.models import Role

logger = logging.getLogger(__name__)

_GROUP_ROLE_MAP: Dict[str, Role] = {
    "netscan-admins": Role.ADMIN,
    "netscan-operators": Role.OPERATOR,
}


def map_groups_to_role(groups: List[str]) -> Role:
    """Map LDAP group names to a NetScan role. Default is READ_ONLY."""
    for group in groups:
        role = _GROUP_ROLE_MAP.get(group.lower())
        if role:
            return role
    return Role.READ_ONLY


def _ldap_authenticate_sync(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Synchronous LDAP authentication. Called via asyncio.to_thread to avoid blocking."""
    try:
        import ldap
        from ldap.filter import escape_filter_chars
    except ImportError:
        logger.error("python-ldap is not installed. Install it with: pip install python-ldap")
        return None

    conn = None
    try:
        conn = ldap.initialize(settings.LDAP_SERVER_URI)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 10)

        if settings.LDAP_START_TLS:
            conn.start_tls_s()

        if settings.LDAP_CA_CERT_FILE:
            conn.set_option(ldap.OPT_X_TLS_CACERTFILE, settings.LDAP_CA_CERT_FILE)

        conn.simple_bind_s(settings.LDAP_BIND_DN, settings.LDAP_BIND_PASSWORD)

        safe_username = escape_filter_chars(username)
        search_filter = settings.LDAP_USER_SEARCH_FILTER.format(username=safe_username)
        results = conn.search_s(settings.LDAP_USER_SEARCH_BASE, ldap.SCOPE_SUBTREE, search_filter, ["dn"])
        if not results:
            logger.warning("LDAP user not found: %s", username)
            return None

        user_dn = results[0][0]

        try:
            user_conn = ldap.initialize(settings.LDAP_SERVER_URI)
            user_conn.set_option(ldap.OPT_REFERRALS, 0)
            user_conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 10)
            if settings.LDAP_START_TLS:
                user_conn.start_tls_s()
            user_conn.simple_bind_s(user_dn, password)
            user_conn.unbind_s()
        except ldap.INVALID_CREDENTIALS:
            logger.warning("LDAP auth failed for %s: invalid credentials", username)
            return None

        groups: List[str] = []
        if settings.LDAP_GROUP_SEARCH_BASE:
            group_filter = settings.LDAP_GROUP_SEARCH_FILTER.format(user_dn=user_dn)
            group_results = conn.search_s(
                settings.LDAP_GROUP_SEARCH_BASE,
                ldap.SCOPE_SUBTREE,
                group_filter,
                ["cn"],
            )
            for _, attrs in group_results:
                if "cn" in attrs:
                    groups.extend(attrs["cn"])

        return {"username": username, "dn": user_dn, "groups": groups}

    except ldap.LDAPError as e:
        logger.error("LDAP error for %s: %s", username, e)
        return None
    finally:
        if conn:
            try:
                conn.unbind_s()
            except Exception:
                pass


async def ldap_authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Async LDAP authentication. Offloads sync I/O to a thread."""
    if not settings.LDAP_ENABLED:
        return None
    return await asyncio.to_thread(_ldap_authenticate_sync, username, password)
