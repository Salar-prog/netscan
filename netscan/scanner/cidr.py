import ipaddress
from typing import List, Tuple


def validate_and_normalize_cidr(cidr_str: str) -> str:
    """Validate and normalize an IPv4 CIDR string (e.g. '192.168.1.0/24')."""
    try:
        network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
        return str(network)
    except ValueError as e:
        raise ValueError(f"Invalid IPv4 CIDR '{cidr_str}': {e}") from e


def expand_cidr_hosts(cidr_str: str, include_network_broadcast: bool = False) -> List[str]:
    """
    Expand a CIDR block into a list of host IP address strings.
    For /31 and /32, returns all addresses.
    For /30 and larger, returns usable hosts unless include_network_broadcast is True.
    """
    network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
    if network.prefixlen >= 31 or include_network_broadcast:
        return [str(ip) for ip in network]
    return [str(ip) for ip in network.hosts()]


def get_subnet_metadata(cidr_str: str) -> dict:
    """Return total hosts, netmask, network address, broadcast address for a CIDR."""
    network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
    usable_hosts = len(expand_cidr_hosts(cidr_str, include_network_broadcast=False))
    return {
        "cidr": str(network),
        "network_address": str(network.network_address),
        "broadcast_address": str(network.broadcast_address),
        "netmask": str(network.netmask),
        "prefix_length": network.prefixlen,
        "total_addresses": network.num_addresses,
        "usable_hosts": usable_hosts,
    }


def is_ip_in_cidr(ip_str: str, cidr_str: str) -> bool:
    """Check if an IP address belongs to a CIDR network."""
    try:
        ip = ipaddress.IPv4Address(ip_str.strip())
        network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
        return ip in network
    except ValueError:
        return False
