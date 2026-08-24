# NetScan

Production-grade IP discovery and availability tracking platform.

NetScan reconciles active network probes (L2 ARP, L3 ICMP, L4 TCP SYN) with managed subnet pools to provide safe, real-time visibility into which IP addresses are active, quarantined, reserved, or available for allocation.

## Features

- **Safe Availability & Quarantine** -- Avoids naive "ping failure = free" assumptions. Unresponsive hosts enter `UNCERTAIN_FIREWALLED` and are only released after meeting both miss thresholds and quarantine duration.
- **Multi-Probe Engine** -- Auto-detects Linux capabilities for ARP/TCP SYN stealth sweeps, with fallback to unprivileged TCP Connect.
- **API-First** -- Full REST API with OpenAPI docs. Programmatic subnet management, IP provisioning queries, and per-IP audit history.
- **Outbound Webhooks** -- HMAC-SHA256 signed event notifications with full IP object snapshots.
- **In-Process Scheduler** -- Background scanning with zero external dependencies (no Redis/Celery).
- **HTMX Dashboard** -- Server-rendered CIDR matrix grid, IP inspector drawer, scan job monitor. No Node.js build step.

## Quickstart

### Requirements

- Python 3.10+
- `nmap` installed on the host (`sudo apt install nmap` on Debian/Ubuntu)

### Install & Run

```bash
pip install -e .
uvicorn netscan.main:app --host 0.0.0.0 --port 8000 --reload
```

- Dashboard: http://localhost:8000/
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker

```bash
docker build -t netscan .
docker run -p 8000:8000 -e SECRET_KEY=your-secret-key netscan
```

Or with docker-compose:

```yaml
services:
  netscan:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SECRET_KEY=your-secret-key
      - DEBUG=false
      - ALLOWED_ORIGINS=https://your-domain.com
    volumes:
      - netscan-data:/app/netscan.db

volumes:
  netscan-data:
```

## Configuration

All settings are configured via environment variables or a `.env` file in the project root.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug logging and relaxed security |
| `SECRET_KEY` | *(empty)* | **Required in production.** Used for session signing. |
| `DATABASE_URL` | `sqlite:///./netscan.db` | Database connection string |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `DEFAULT_SCAN_INTERVAL_MINUTES` | `60` | Default scan interval per subnet |
| `DEFAULT_MISS_THRESHOLD` | `3` | Consecutive misses before uncertain state |
| `DEFAULT_QUARANTINE_HOURS` | `48` | Hours before uncertain host can become available |
| `NMAP_TIMEOUT_SECONDS` | `300` | Per-scan timeout |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Outbound webhook timeout |
| `WEBHOOK_MAX_RETRIES` | `3` | Webhook delivery retry count |

## API Key Setup

All API endpoints require authentication via `X-API-Key` header. Create your first key via the bootstrap endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"name": "my-admin-key"}'
```

The response contains your `raw_key` -- store it safely, it is never shown again. Subsequent keys require an existing key:

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: <your-existing-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "automation-key", "role": "operator"}'
```

## API Examples

**Find next available IPs (for Terraform/provisioning):**

```bash
curl -H "X-API-Key: <key>" \
  "http://localhost:8000/api/v1/ips/available?subnet_id=<SUBNET_UUID>&count=3"
```

**Trigger a subnet scan:**

```bash
curl -X POST -H "X-API-Key: <key>" \
  http://localhost:8000/api/v1/subnets/<SUBNET_UUID>/scan
```

**Inspect IP history:**

```bash
curl -H "X-API-Key: <key>" \
  http://localhost:8000/api/v1/ips/192.168.1.50/history
```

## Development

```bash
pip install -e ".[test]"
pytest -v
```

The test suite uses an in-memory SQLite database and does not require nmap or API keys.

## License

[MIT](LICENSE)
