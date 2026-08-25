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
  -d '{"status": "reserved", "note": "k8s node 3"}'
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
| `DELETE` | `/api/v1/auth/keys/{id}` | Revoke key |

---

## Rate Limiting

Global: 120 requests/minute per IP. `/health` is exempt.

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid API key |
| `403` | Valid key but insufficient role |
| `404` | Resource not found |
| `409` | Conflict (e.g. scan already running) |
| `422` | Validation error (check response body) |
| `429` | Rate limit exceeded |
