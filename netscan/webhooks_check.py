import ipaddress
import socket
from urllib.parse import urlparse

from netscan.config import settings


def is_url_blocked(url: str) -> bool:
    """Check if URL points to a private/internal IP range."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            try:
                resolved = socket.getaddrinfo(hostname, None)
                ip = ipaddress.ip_address(resolved[0][4][0])
            except (socket.gaierror, IndexError):
                return False

        blocked = [
            ipaddress.ip_network(cidr.strip()) for cidr in settings.WEBHOOK_BLOCKED_RANGES.split(",") if cidr.strip()
        ]

        return any(ip in network for network in blocked)
    except Exception:
        return False
