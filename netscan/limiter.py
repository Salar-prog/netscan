from fastapi import Request
from slowapi import Limiter
from netscan.config import settings


def get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For from trusted proxies."""
    client_ip = request.client.host if request.client else "unknown"

    trusted = {ip.strip() for ip in settings.TRUSTED_PROXIES.split(",") if ip.strip()}
    if trusted and client_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return client_ip


limiter = Limiter(key_func=get_client_ip, default_limits=[settings.RATE_LIMIT_DEFAULT])
