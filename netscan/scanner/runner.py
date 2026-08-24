import asyncio
import os
import shutil
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from netscan.config import settings
from netscan.models import DiscoveryMethod


@dataclass
class PortInfo:
    port: int
    protocol: str
    state: str
    service: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class HostProbeResult:
    ip: str
    is_up: bool
    status_reason: str
    discovery_method: DiscoveryMethod
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    mac_vendor: Optional[str] = None
    open_ports: List[PortInfo] = field(default_factory=list)
    raw_extra: Dict[str, Any] = field(default_factory=dict)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class NmapScanner:
    """Multi-probe Nmap runner with capability detection and XML parsing."""

    def __init__(self):
        self.nmap_path = shutil.which("nmap")
        self.is_privileged = self._detect_raw_socket_privileges()

    @staticmethod
    def _detect_raw_socket_privileges() -> bool:
        """Detect if the current process has raw socket capabilities (root or CAP_NET_RAW)."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            s.close()
            return True
        except (PermissionError, OSError):
            return False

    def build_nmap_args(self, target: str, scan_ports: bool = True) -> List[str]:
        """Construct Nmap CLI arguments based on privileges and port probing requirements."""
        if not self.nmap_path:
            raise RuntimeError("Nmap binary not found on system PATH. Please install nmap.")

        ports = settings.TOP_TCP_PORTS
        timing = settings.NMAP_TIMING_TEMPLATE

        args = [self.nmap_path, "-oX", "-", timing, "-R"]

        if self.is_privileged:
            if scan_ports:
                args += ["-sS", "-PR", "-PE", "-PP", f"-PS{ports}", f"-p{ports}", "--version-light"]
            else:
                args += ["-sn", "-PR", "-PE", "-PP", f"-PS{ports}"]
        else:
            if scan_ports:
                args += ["-sT", f"-p{ports}"]
            else:
                args += ["-sn", "-PE", f"-PA{ports}"]

        args.append(target)
        return args

    async def scan_cidr(self, cidr: str, scan_ports: bool = True) -> Dict[str, HostProbeResult]:
        """Execute Nmap scan on target CIDR and parse results into HostProbeResult objects."""
        args = self.build_nmap_args(cidr, scan_ports=scan_ports)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.NMAP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(f"Nmap scan timed out after {settings.NMAP_TIMEOUT_SECONDS} seconds for {cidr}")

        if process.returncode != 0 and not stdout:
            err_msg = stderr.decode(errors="replace")
            raise RuntimeError(f"Nmap exited with code {process.returncode}: {err_msg}")

        return self.parse_nmap_xml(stdout.decode(errors="replace"))

    def parse_nmap_xml(self, xml_content: str) -> Dict[str, HostProbeResult]:
        """Parse Nmap XML string into a mapping of IP -> HostProbeResult."""
        results: Dict[str, HostProbeResult] = {}
        if not xml_content.strip():
            return results

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse Nmap XML output: {e}") from e

        for host_elem in root.findall("host"):
            status_elem = host_elem.find("status")
            if status_elem is None:
                continue

            state = status_elem.get("state", "down")
            reason = status_elem.get("reason", "unknown")
            is_up = state == "up"

            ip_address: Optional[str] = None
            mac_address: Optional[str] = None
            mac_vendor: Optional[str] = None

            for addr in host_elem.findall("address"):
                addr_type = addr.get("addrtype")
                if addr_type == "ipv4":
                    ip_address = addr.get("addr")
                elif addr_type == "mac":
                    mac_address = addr.get("addr")
                    mac_vendor = addr.get("vendor")

            if not ip_address:
                continue

            hostname: Optional[str] = None
            hostnames_elem = host_elem.find("hostnames")
            if hostnames_elem is not None:
                first_h = hostnames_elem.find("hostname")
                if first_h is not None:
                    hostname = first_h.get("name")

            discovery_method = self._map_reason_to_method(reason, mac_address is not None)

            open_ports: List[PortInfo] = []
            ports_elem = host_elem.find("ports")
            if ports_elem is not None:
                for port_elem in ports_elem.findall("port"):
                    port_id = int(port_elem.get("portid", "0"))
                    protocol = port_elem.get("protocol", "tcp")
                    port_state_elem = port_elem.find("state")
                    port_state = port_state_elem.get("state", "closed") if port_state_elem is not None else "closed"
                    port_reason = port_state_elem.get("reason", "") if port_state_elem is not None else ""

                    service_name: Optional[str] = None
                    product: Optional[str] = None
                    version: Optional[str] = None
                    service_elem = port_elem.find("service")
                    if service_elem is not None:
                        service_name = service_elem.get("name")
                        product = service_elem.get("product")
                        version = service_elem.get("version")

                    if port_state in ("open", "open|filtered"):
                        open_ports.append(
                            PortInfo(
                                port=port_id,
                                protocol=protocol,
                                state=port_state,
                                service=service_name,
                                product=product,
                                version=version,
                                reason=port_reason,
                            )
                        )

            results[ip_address] = HostProbeResult(
                ip=ip_address,
                is_up=is_up,
                status_reason=reason,
                discovery_method=discovery_method,
                hostname=hostname,
                mac_address=mac_address,
                mac_vendor=mac_vendor,
                open_ports=open_ports,
                raw_extra={"state": state, "reason": reason},
            )

        return results

    @staticmethod
    def _map_reason_to_method(reason: str, has_mac: bool) -> DiscoveryMethod:
        r = reason.lower()
        if "arp" in r or has_mac:
            return DiscoveryMethod.ARP
        if "echo" in r or "timestamp" in r or "icmp" in r:
            return DiscoveryMethod.ICMP
        if "syn-ack" in r:
            return DiscoveryMethod.TCP_SYN
        if "conn-refused" in r or "reset" in r or "response" in r:
            return DiscoveryMethod.TCP_CONNECT
        return DiscoveryMethod.TCP_CONNECT
