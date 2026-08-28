# NetScan

[![CI](https://github.com/Salar-prog/netscan/actions/workflows/ci.yml/badge.svg)](https://github.com/Salar-prog/netscan/actions/workflows/ci.yml)

IP discovery that doesn't lie to you.

NetScan scans your subnets, tracks what's alive, and won't free an IP just because a firewall dropped a ping. Unresponsive hosts enter quarantine — they stay marked uncertain until they've missed enough consecutive scans *and* waited out a configurable cooldown. No false frees.

## Quick Start

```bash
pip install -e ".[test,ldap]"
netscan serve
```

> Building from source needs `libldap2-dev` and `libsasl2-dev` system headers (see [Development](#development)). The Docker image has no such requirement. Install without `.[ldap]` if you don't need LDAP/AD authentication.

Dashboard at `http://localhost:8000/`. Swagger at `/docs`.

## The Dashboard

The dashboard is the main interface. Everything you need is one click away.

**CIDR Matrix** — Every subnet rendered as a color-coded grid. Green = active, yellow = uncertain (firewalled), red = unreachable, gray = available. Click any IP to inspect.

**IP Inspector** — Side drawer slides out with full IP detail: current status, last seen, scan history, reservation note. Reserve or release IPs inline.

**Scan Job Monitor** — Live view of running scans with status updates (QUEUED → RUNNING → COMPLETED). See which subnets are being scanned and when they finished.

**Settings** — Generate API keys, manage webhooks, configure scan intervals. One page, no digging through config files.

**Provision Helper** — Find the next N available IPs in a subnet. Feed the output straight into Terraform or your provisioning tool.

## Features

- **Safe quarantine model** — "ping failed" never means "free to use"
- **Multi-probe engine** — ARP, ICMP, TCP SYN with auto-detection and fallback
- **HTMX dashboard** — no Node.js, no build step, server-rendered
- **Structured error responses** — machine-parseable `{error_code, message, details}` envelope
- **Idempotency keys** — `Idempotency-Key` header prevents duplicate writes
- **Outbound webhooks** — HMAC-SHA256 signed, with retry and exponential backoff
- **In-process scheduler** — background scans, zero external deps
- **LDAP/AD auth** — corporate credentials for dashboard, API keys for scripts
- **Rate limiting** — configurable per-IP limit via slowapi
- **Structured logging** — JSON or text, configurable level
- **API key lifecycle** — soft-revoke, rename, reassign role, set expiry
- **Correlation IDs** — `X-Request-ID` header on every request, in access logs
- **Prometheus metrics** — `/metrics` endpoint with scan/webhook counters
- **Retention policy** — configurable pruning of old scan jobs and IP history
- **Overlapping-subnet detection** — rejects CIDRs that overlap with existing subnets
- **Postgres support** — tested in CI, works via `DATABASE_URL`

## Configuration

Environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Debug logging, relaxed security |
| `SECRET_KEY` | *(empty)* | **Required in production.** Session signing. |
| `DATABASE_URL` | `sqlite:///./netscan.db` | Database URL |
| `ALLOWED_ORIGINS` | *(empty)* | Comma-separated CORS origins (empty = no CORS) |
| `RATE_LIMIT_DEFAULT` | `120/minute` | Global rate limit per IP |
| `DEFAULT_SCAN_INTERVAL_MINUTES` | `60` | Scan interval per subnet |
| `DEFAULT_MISS_THRESHOLD` | `3` | Consecutive misses before uncertain |
| `DEFAULT_QUARANTINE_HOURS` | `48` | Cooldown before uncertain → available |
| `NMAP_TIMEOUT_SECONDS` | `300` | Per-scan timeout |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Outbound webhook timeout |
| `WEBHOOK_MAX_RETRIES` | `3` | Webhook retry count |
| `LOG_FORMAT` | `text` | `text` or `json` |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `LDAP_ENABLED` | `false` | Enable LDAP/AD dashboard auth |
| `LDAP_SERVER_URI` | *(empty)* | e.g. `ldap://dc01.corp.local` |
| `LDAP_BIND_DN` | *(empty)* | Service account DN |
| `LDAP_BIND_PASSWORD` | *(empty)* | Service account password |
| `LDAP_USER_SEARCH_BASE` | *(empty)* | OU containing users |
| `LDAP_USER_SEARCH_FILTER` | `(sAMAccountName={username})` | User lookup filter |
| `LDAP_GROUP_SEARCH_BASE` | *(empty)* | OU containing groups |
| `LDAP_GROUP_SEARCH_FILTER` | `(member={user_dn})` | Group membership filter |
| `LDAP_START_TLS` | `false` | Use StartTLS |
| `LDAP_CA_CERT_FILE` | *(empty)* | CA cert for LDAP TLS |
| `DISABLE_BOOTSTRAP` | `false` | Disable HTTP bootstrap endpoint |
| `RETENTION_DAYS` | `90` | Prune old scan jobs and IP history (0 = disabled) |
| `SCHEDULER_ENABLED` | `true` | Enable in-process scheduler (set false on all but one replica) |

## Docker

Prebuilt images are published to GitHub Container Registry on every release:

```bash
docker pull ghcr.io/salar-prog/netscan:latest   # or pin: 0.1.0 / 0.1
docker run -p 8000:8000 -e SECRET_KEY=your-secret-key \
  ghcr.io/salar-prog/netscan:latest
```

Or build from source:

```bash
docker build -t netscan .
docker run -p 8000:8000 -e SECRET_KEY=your-secret-key netscan
```

For ARP/SYN stealth scanning, add network capabilities:

```bash
docker run -p 8000:8000 \
  --cap-add=NET_RAW --cap-add=NET_ADMIN \
  -e SECRET_KEY=your-secret-key netscan
```

<details>
<summary>docker-compose</summary>

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
    cap_add:
      - NET_RAW
      - NET_ADMIN
    volumes:
      - netscan-data:/app/netscan.db

volumes:
  netscan-data:
```

</details>

**Single-instance constraint:** NetScan uses SQLite (WAL mode) and an in-process scheduler. Run exactly one worker and one container per database — multiple instances will duplicate scheduled scans and corrupt concurrent writes. For production, use PostgreSQL (`DATABASE_URL=postgresql://...`) — tested in CI.

## CLI

```
netscan serve                          # Dashboard + API
netscan serve --no-dashboard           # API only
netscan serve --reload                 # Dev mode
netscan serve --host 0.0.0.0 --port 9000
netscan login                          # LDAP auth → create API key
```

## API

Full REST API with OpenAPI docs. [API Reference →](docs/api.md)

Key endpoints:
- `POST /api/v1/subnets` — create subnet (overlapping CIDRs rejected)
- `POST /api/v1/subnets/{id}/scan` — trigger scan
- `GET /api/v1/ips/available` — find next available IPs for provisioning
- `GET /api/v1/ips/{ip}` — inspect IP (accepts optional `subnet_id` param)
- `PATCH /api/v1/auth/keys/{id}` — rename, reassign role, or set expiry
- `DELETE /api/v1/auth/keys/{id}` — soft-revoke (sets `revoked_at`, never hard-deletes)
- `GET /metrics` — Prometheus-format counters
- `GET /health` — database + nmap + scheduler status

## Development

```bash
pip install -e ".[test,ldap]"
pytest -v
ruff check netscan/
ruff format --check netscan/
```

`python-ldap` needs system headers to compile: `sudo apt install libldap2-dev libsasl2-dev` (Debian/Ubuntu) before installing. If you don't need LDAP, install with `pip install -e ".[test]"` instead.

Tests use in-memory SQLite. No nmap or API keys needed. CI runs on every push and PR.

## License

[MIT](LICENSE)
