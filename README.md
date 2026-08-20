# NetScan 📡
### Production-Grade IP Discovery and Availability Platform

NetScan is a lightweight, API-first IP availability tracking and network discovery service. It reconciles active network probes (L2 ARP, L3 ICMP, L4 TCP SYN) with managed subnet pools to provide safe, real-time visibility into which IP addresses are active, quarantined/uncertain, reserved, or available for allocation.

---

## Key Features

- **Safe Availability & Quarantine**: Avoids naive "ping failure = free" assumptions. Firewalled or transiently unresponsive hosts enter an `UNCERTAIN_FIREWALLED` state and are only released to `AVAILABLE_CANDIDATE` after meeting both consecutive miss thresholds and configurable quarantine time windows.
- **Multi-Probe Engine**: Auto-detects Linux capabilities (`CAP_NET_RAW` / root) to perform stealth L2 ARP sweeps and L4 TCP SYN probes (`-sS`), with seamless fallback to unprivileged TCP Connect sweeps (`-sT`).
- **API-First & Automation Ready**: Full OpenAPI/REST endpoints for programmatic subnet management, instant "find next $K$ available IPs" queries for Terraform/provisioning pipelines, and per-IP audit history.
- **Outbound Webhooks**: Dispatches HMAC-SHA256 signed event notifications with complete IP object snapshots (`ip.state_changed`, `scan.completed`).
- **In-Process Scheduler**: Background scanning orchestrated with zero external message broker dependencies (no Redis or Celery needed).
- **HTMX & Tailwind Dashboard**: High-reactivity server-rendered visual CIDR matrix grid, IP inspector slide-over drawer, and scan job monitor.

---

## Quickstart

### 1. Requirements
- Python 3.10+
- `nmap` installed on system (`sudo apt install nmap` on Debian/Ubuntu)

### 2. Installation
```bash
pip install -e .
```

Or install dependencies directly:
```bash
pip install fastapi uvicorn sqlmodel pydantic-settings apscheduler httpx jinja2 python-multipart
```

### 3. Run Application
```bash
uvicorn netscan.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Web Dashboard**: [http://localhost:8000/](http://localhost:8000/)
- **Interactive OpenAPI (Swagger) Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## API Highlights

### Find Next Available IPs (for Automated VM/Host Provisioning)
```bash
curl -X GET "http://localhost:8000/api/v1/ips/available?subnet_id=<SUBNET_UUID>&count=3"
```
**Response:**
```json
{
  "subnet_id": "8f889218-1d2a-43c2-bf72-4b2a65a3962d",
  "cidr": "192.168.1.0/24",
  "requested_count": 3,
  "available_ips": [
    "192.168.1.15",
    "192.168.1.16",
    "192.168.1.17"
  ],
  "count_returned": 3
}
```

### Inspect IP Address & Audit History
```bash
curl -X GET "http://localhost:8000/api/v1/ips/192.168.1.50/history"
```

### Trigger Subnet Scan
```bash
curl -X POST "http://localhost:8000/api/v1/subnets/<SUBNET_UUID>/scan"
```

---

## Running Tests

```bash
pytest -v
```
