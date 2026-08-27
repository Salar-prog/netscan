# NetScan API Reference

All endpoints live under `/api/v1` and require an `X-API-Key` header (except bootstrap).

Interactive docs: `/docs` (Swagger) or `/redoc` (ReDoc).

> The web dashboard does **not** call these endpoints directly — its HTMX forms go through separate session-cookie-authenticated proxy routes under `/web/*`. Those routes are internal to the dashboard and not part of the public API.

---

## Authentication

Every request needs `X-API-Key: <your-key>`.

**Create your first key:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"name": "my-admin-key"}'
```

Response includes `raw_key` — store it, it's never shown again.

**Create additional keys:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: <existing-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "automation-key", "role": "operator"}'
```

Roles: `admin` (full access), `operator` (scan + read), `read_only` (read only).

---

## Subnets

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/subnets` | List all subnets |
| `POST` | `/api/v1/subnets` | Create a subnet |
| `GET` | `/api/v1/subnets/{id}` | Get subnet details |
| `PATCH` | `/api/v1/subnets/{id}` | Update subnet |
| `DELETE` | `/api/v1/subnets/{id}` | Delete subnet |
| `GET` | `/api/v1/subnets/{id}/matrix` | IP status matrix |
| `POST` | `/api/v1/subnets/{id}/scan` | Trigger a scan |

**Create subnet:**

```bash
curl -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"cidr": "192.168.1.0/24", "name": "office-lan"}'
```

**Trigger scan:**

```bash
curl -X POST -H "X-API-Key: <key>" \
  http://localhost:8000/api/v1/subnets/<SUBNET_ID>/scan
```

---

## IP Addresses

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/ips` | List all IPs (filter by `subnet_id`, `status`) |
| `GET` | `/api/v1/ips/available` | Next available IPs (params: `subnet_id`, `count`) |
| `GET` | `/api/v1/ips/{ip}` | IP detail |
| `PATCH` | `/api/v1/ips/{ip}` | Reserve/release IP |
| `GET` | `/api/v1/ips/{ip}/history` | Audit trail |

**Find available IPs (for Terraform/provisioning):**

```bash
curl -H "X-API-Key: <key>" \
  "http://localhost:8000/api/v1/ips/available?subnet_id=<ID>&count=3"
```

**Reserve an IP:**

```bash
curl -X PATCH -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/ips/192.168.1.50 \
  -d '{"is_reserved": true, "hostname": "k8s-node-3"}'
```

---

## Scan Jobs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/scans` | List all scan jobs |
| `GET` | `/api/v1/scans/{id}` | Scan job detail |

---

## Webhooks

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/webhooks` | List webhooks |
| `POST` | `/api/v1/webhooks` | Create webhook |
| `DELETE` | `/api/v1/webhooks/{id}` | Delete webhook |
| `POST` | `/api/v1/webhooks/{id}/test` | Send test event |

**Create webhook:**

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hooks.slack.com/...", "events": ["scan.completed"]}'
```

Response includes `secret` — store it for HMAC signature verification.

**Events:** `scan.completed`, `scan.failed`, `ip.status_changed`, `subnet.created`, `subnet.deleted`

**HMAC verification:** Each delivery includes `X-Webhook-Signature` header (HMAC-SHA256 of the JSON body using the webhook secret).

---

## API Key Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/auth/keys` | List keys |
| `POST` | `/api/v1/auth/keys` | Create key |
| `POST` | `/api/v1/auth/keys/bootstrap` | Create first key (open until first key exists) |
| `PATCH` | `/api/v1/auth/keys/{id}` | Rename, reassign role, or set expiry |
| `DELETE` | `/api/v1/auth/keys/{id}` | Soft-revoke key (sets `revoked_at`) |

**Update a key:**

```bash
curl -X PATCH http://localhost:8000/api/v1/auth/keys/<KEY_ID> \
  -H "X-API-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "new-name", "role": "operator", "expires_at": "2026-12-31T23:59:59Z"}'
```

---

## Rate Limiting

Global rate limit per IP. Default: `120/minute`. Configurable via `RATE_LIMIT_DEFAULT`.
`/health` is exempt.

---

## Error Responses

All errors return a structured JSON envelope:

```json
{
  "error_code": "SUBNET_NOT_FOUND",
  "message": "Subnet not found",
  "details": {}
}
```

| Status | Error Code | Meaning |
|--------|-----------|---------|
| `400` | `INVALID_CIDR` | Malformed or oversized CIDR (max /24) |
| `400` | `SSRF_BLOCKED` | Webhook URL targets private/metadata IP |
| `401` | *(missing)* | Missing or invalid API key |
| `403` | *(missing)* | Valid key but insufficient role |
| `404` | `SUBNET_NOT_FOUND` | Subnet does not exist |
| `404` | `IP_NOT_FOUND` | IP does not exist |
| `404` | `SCAN_NOT_FOUND` | Scan job does not exist |
| `404` | `WEBHOOK_NOT_FOUND` | Webhook does not exist |
| `409` | `SUBNET_EXISTS` | CIDR already registered |
| `400` | `SUBNET_OVERLAPS` | CIDR overlaps with existing subnet |
| `409` | `SCAN_ALREADY_RUNNING` | Active scan exists for this subnet |
| `409` | `BOOTSTRAP_RACE` | Two bootstrap requests raced; retry |
| `422` | *(validation)* | Pydantic validation error (check `detail`) |
| `429` | *(missing)* | Rate limit exceeded |
| `500` | `BOOTSTRAP_DISABLED` | First API key already exists |

---

## Idempotency

POST, PUT, PATCH, and DELETE endpoints support idempotent retries via the `Idempotency-Key` header:

```bash
curl -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: <key>" \
  -H "Idempotency-Key: my-unique-request-id" \
  -H "Content-Type: application/json" \
  -d '{"cidr": "10.0.0.0/24", "name": "test"}'
```

- Keys are scoped to the HTTP method + path + request body.
- Cached responses are returned for **24 hours**.
- Without the header, requests are not idempotent.

---

## Metrics

`GET /metrics` returns Prometheus-format counters:

```
netscan_subnets_total <count>
netscan_ips_total <count>
netscan_scans_total <count>
```

No authentication required.

---

## Correlation IDs

Every request gets an `X-Request-ID` header (UUID). If the client sends one, it's echoed back. The ID appears in access logs and response headers for request tracing.

---

## Health Check

`GET /health` returns service status including database, nmap, and scheduler liveness. No authentication required.

```json
{
  "status": "healthy",
  "service": "NetScan",
  "version": "0.2.0",
  "checks": {
    "database": "ok",
    "nmap": "ok",
    "scheduler": "ok"
  }
}
```

---

## Pagination

List endpoints (`GET /subnets`, `GET /ips`, `GET /scans`) support `limit` and `offset` query parameters:

```bash
curl -H "X-API-Key: <key>" \
  "http://localhost:8000/api/v1/subnets?limit=10&offset=20"
```
