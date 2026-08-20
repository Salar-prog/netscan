from netscan.models import DiscoveryMethod
from netscan.scanner.runner import NmapScanner

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
