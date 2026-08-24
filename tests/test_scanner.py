from netscan.models import DiscoveryMethod
from netscan.scanner.runner import NmapScanner

import pytest

SAMPLE_NMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nmaprun>
<nmaprun scanner="nmap" args="nmap -sS -PR -PE -PP -p80,443 -oX - 192.168.1.0/24" start="1700000000" version="7.94">
<host>
    <status state="up" reason="arp-response" reason_ttl="0"/>
    <address addr="192.168.1.1" addrtype="ipv4"/>
    <address addr="00:11:22:33:44:55" addrtype="mac" vendor="Netgear"/>
    <hostnames>
        <hostname name="router.localdomain" type="PTR"/>
    </hostnames>
    <ports>
        <port protocol="tcp" portid="80">
            <state state="open" reason="syn-ack" reason_ttl="64"/>
            <service name="http" product="lighttpd" version="1.4.67"/>
        </port>
        <port protocol="tcp" portid="443">
            <state state="closed" reason="reset" reason_ttl="64"/>
        </port>
    </ports>
</host>
<host>
    <status state="up" reason="echo-reply" reason_ttl="128"/>
    <address addr="192.168.1.50" addrtype="ipv4"/>
    <hostnames>
        <hostname name="win-server.corp" type="PTR"/>
    </hostnames>
    <ports>
        <port protocol="tcp" portid="443">
            <state state="open" reason="syn-ack" reason_ttl="128"/>
            <service name="https" product="Microsoft HTTPAPI" version="2.0"/>
        </port>
    </ports>
</host>
</nmaprun>
"""


def test_nmap_xml_parsing():
    scanner = NmapScanner()
    results = scanner.parse_nmap_xml(SAMPLE_NMAP_XML)

    assert len(results) == 2
    assert "192.168.1.1" in results
    assert "192.168.1.50" in results

    # Host 1: ARP & MAC
    h1 = results["192.168.1.1"]
    assert h1.is_up is True
    assert h1.mac_address == "00:11:22:33:44:55"
    assert h1.mac_vendor == "Netgear"
    assert h1.hostname == "router.localdomain"
    assert h1.discovery_method == DiscoveryMethod.ARP
    assert len(h1.open_ports) == 1
    assert h1.open_ports[0].port == 80
    assert h1.open_ports[0].service == "http"
    assert h1.open_ports[0].product == "lighttpd"

    # Host 2: ICMP & TCP SYN
    h2 = results["192.168.1.50"]
    assert h2.is_up is True
    assert h2.mac_address is None
    assert h2.hostname == "win-server.corp"
    assert h2.discovery_method == DiscoveryMethod.ICMP
    assert len(h2.open_ports) == 1
    assert h2.open_ports[0].port == 443


def test_parse_empty_output_returns_empty_dict():
    scanner = NmapScanner()
    assert scanner.parse_nmap_xml(" ") == {}
    assert scanner.parse_nmap_xml("") == {}


def test_parse_invalid_xml_raises_value_error():
    scanner = NmapScanner()
    with pytest.raises(ValueError):
        scanner.parse_nmap_xml("<not-valid-xml")


def test_parse_skips_hosts_without_status_or_ip():
    xml = """<?xml version="1.0"?>
<nmaprun>
<host>
    <address addr="10.0.0.9" addrtype="ipv4"/>
</host>
<host>
    <status state="down" reason="no-response"/>
    <address addr="10.0.0.8" addrtype="ipv4"/>
</host>
</nmaprun>
"""
    scanner = NmapScanner()
    results = scanner.parse_nmap_xml(xml)

    assert "10.0.0.9" not in results
    assert results["10.0.0.8"].is_up is False
    assert results["10.0.0.8"].open_ports == []


def test_parse_includes_open_filtered_and_excludes_closed_ports():
    xml = """<?xml version="1.0"?>
<nmaprun>
<host>
    <status state="up" reason="syn-ack"/>
    <address addr="10.0.0.7" addrtype="ipv4"/>
    <ports>
        <port protocol="tcp" portid="80">
            <state state="open|filtered" reason="no-response"/>
        </port>
        <port protocol="tcp" portid="443">
            <state state="closed" reason="reset"/>
        </port>
    </ports>
</host>
</nmaprun>
"""
    scanner = NmapScanner()
    results = scanner.parse_nmap_xml(xml)
    ports = results["10.0.0.7"].open_ports

    assert [p.port for p in ports] == [80]
    assert ports[0].state == "open|filtered"


@pytest.mark.parametrize(
    "reason,has_mac,expected",
    [
        ("arp-response", False, DiscoveryMethod.ARP),
        ("echo-reply", False, DiscoveryMethod.ICMP),
        ("timestamp-reply", False, DiscoveryMethod.ICMP),
        ("syn-ack", False, DiscoveryMethod.TCP_SYN),
        ("reset", False, DiscoveryMethod.TCP_CONNECT),
        ("unknown-reason", False, DiscoveryMethod.TCP_CONNECT),
        ("unknown-reason", True, DiscoveryMethod.ARP),
    ],
)
def test_map_reason_to_method(reason, has_mac, expected):
    assert NmapScanner._map_reason_to_method(reason, has_mac) == expected


def test_build_nmap_args_privileged_with_ports():
    scanner = NmapScanner()
    scanner.nmap_path = "/usr/bin/nmap"
    scanner.is_privileged = True

    args = scanner.build_nmap_args("192.168.1.0/24", scan_ports=True)

    assert args[0] == "/usr/bin/nmap"
    assert "-sS" in args
    assert "-PR" in args
    assert args[-1] == "192.168.1.0/24"


def test_build_nmap_args_unprivileged_without_ports():
    scanner = NmapScanner()
    scanner.nmap_path = "/usr/bin/nmap"
    scanner.is_privileged = False

    args = scanner.build_nmap_args("192.168.1.0/24", scan_ports=False)

    assert "-sT" not in args
    assert "-sn" in args
    assert "-PE" in args


def test_build_nmap_args_raises_when_nmap_missing():
    scanner = NmapScanner()
    scanner.nmap_path = None

    with pytest.raises(RuntimeError):
        scanner.build_nmap_args("192.168.1.0/24")

