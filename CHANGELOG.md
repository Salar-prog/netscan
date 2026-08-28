# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Key expiry** — API keys support `expires_at` field; expired keys rejected at auth layer
- **Retention policy** — `RETENTION_DAYS` setting (default 90); old ip_history and scan_jobs pruned on startup
- **Metrics endpoint** — `/metrics` exposes basic Prometheus-format counters (subnets, IPs, scans)
- **Scoped IP lookup** — `GET /ips/{ip}` accepts optional `subnet_id` query parameter
- **Scheduler health** — `/health` now verifies scheduler liveness
- **Bootstrap kill-switch** — `DISABLE_BOOTSTRAP` setting to disable HTTP bootstrap endpoint
- **Overlapping-subnet detection** — `POST /subnets` rejects CIDRs that overlap with existing subnets
- **Soft key revoke** — `DELETE /auth/keys/{id}` sets `revoked_at` instead of hard-delete
- **Key PATCH endpoint** — `PATCH /auth/keys/{id}` to rename, reassign role, or set expiry
- **Correlation IDs** — `X-Request-ID` header generated per request, included in access logs
- **Graceful shutdown** — lifespan drains in-flight webhook and scan tasks before exit
- **Typed response models** — `SubnetMatrixResponse`, `SubnetScanTriggered`, `AvailableIPsResponse` on key routes
- **Postgres CI** — GitHub Actions runs full test suite against Postgres 16
- **Dual-database test fixture** — conftest detects `DATABASE_URL`, supports SQLite + Postgres
- **Scheduler flag** — `SCHEDULER_ENABLED` setting (default true); set false on all but one replica in multi-instance deployments

### Fixed

- **Zombie process** — `await process.wait()` after `process.kill()` in scanner
- **N+1 subnet listing** — replaced 4-per-subnet count queries with single GROUP BY
- **Proxy-aware access logs** — access log middleware uses shared `get_client_ip()` from rate limiter
- **Services init shadow** — removed singleton re-exports that shadowed module names
- **Version duplication** — `importlib.metadata.version()` replaces hardcoded string
- **Decorative lockfile removed** — `requirements-lock.txt` deleted (CI/Docker use pyproject.toml bounds)
- **Webhook dispatch coverage** — new test exercises scan→webhook dispatch path end-to-end
- **Bootstrap race condition** — `BootstrapLock` singleton row prevents concurrent bootstrap calls from both succeeding
- **Idempotency race condition** — concurrent insert with same key now catches `IntegrityError` and returns winner's response instead of 500
- **Scan task drain** — in-flight scans self-register via `asyncio.current_task()`; drain runs before scheduler shutdown with 30s bounded timeout
- **Migration Postgres compatibility** — fixed `server_default` from SQLite-specific `datetime('now')` to `sa.func.now()`; removed poisoned seed INSERT that broke bootstrap on fresh installs

### Changed

- `DISABLE_BOOTSTRAP` defaults to `false`; set `true` to disable HTTP bootstrap endpoint
- `RETENTION_DAYS` defaults to `90`; set `0` to disable pruning
- Single-instance constraint documented in README

### Added

- **Shared SSRF validation** — single `is_url_blocked()` function in `webhooks_check.py` protects both API and dashboard webhook creation
- **LDAP injection fix** — username escaped with `ldap.filter.escape_filter_chars()` before LDAP bind
- **Async LDAP** — `ldap_authenticate()` wrapped in `asyncio.to_thread()` to avoid blocking the event loop; 10s network timeout
- **Webhook task tracking** — outbound webhook tasks tracked with done-callbacks that log exceptions on failure
- **Targeted webhook test dispatch** — dashboard "Test" button sends to specific webhook, not broadcast
- **Scanner unprivileged warning** — logs WARNING when running without raw socket capabilities
- **python-ldap optional** — moved to `[project.optional-dependencies] ldap`; install with `pip install netscan[ldap]`

### Fixed

- **Secure cookie flag** — session cookies set `secure=True` when `DEBUG=false`
- **Throttled last_used_at** — API key `last_used_at` only written once per hour (reduces write contention)
- **Dashboard count cap** — `/web/ips/available` count parameter capped at 50

### Changed

- `python-ldap` no longer a hard dependency — install with `netscan[ldap]` for LDAP support
- TOCTOU race in `check_active_scan()` documented as accepted risk under single-instance constraint

### Added

- **Structured error responses** — all API errors return `{error_code, message, details}` envelope with machine-parseable codes (`INVALID_CIDR`, `SUBNET_EXISTS`, `SCAN_ALREADY_RUNNING`, `SSRF_BLOCKED`, etc.)
- **Idempotency keys** — `Idempotency-Key` header on POST/PUT/PATCH/DELETE prevents duplicate writes for 24 hours
- **Stale scan job recovery** — QUEUED/RUNNING jobs older than 10 minutes are automatically marked FAILED on startup
- **Concurrent scan guard** — `check_active_scan()` shared across API, scheduler, and executor prevents overlapping scans per subnet
- **Configurable rate limit** — `RATE_LIMIT_DEFAULT` setting (default `120/minute`)
- **CORS lock** — `ALLOWED_ORIGINS` defaults to empty (no origins); CORS middleware skipped when unconfigured
- **Subnets pagination** — `list_subnets` accepts `limit`/`offset` params (consistent with IPs endpoint)
- **Webhook event_id** — UUID in every webhook payload for consumer-side deduplication

### Fixed

- **Docker healthcheck** — removed `create_all()` / Alembic double-CREATE TABLE conflict; Alembic owns schema exclusively
- **In-memory SQLite test isolation** — Alembic receives module-level engine via `config.attributes["connectable"]`, ensuring tests and lifespan share the same connection

### Changed

- `ALLOWED_ORIGINS` default changed from `*` to `""` (empty). Set explicitly to enable CORS.
- Alembic migration failure on startup is now **fatal** (no silent swallow)
- SlowAPI rate limiting wired into ASGI middleware (was inert before)

### Dependencies

- Bumped: pygments 2.20→2.21, typing-extensions 4.15→4.16, hypothesis 6.155→6.165, uvicorn 0.49→0.52, starlette 1.3→1.6
- Bumped: docker/login-action 3→4, docker/metadata-action 5→6, docker/build-push-action 6→7, docker/setup-buildx-action 3→4

## [0.1.0] - 2026-08-25

### Added

- Multi-probe discovery engine (L2 ARP, L3 ICMP, L4 TCP SYN stealth, TCP-connect fallback) with automatic capability detection
- Safe availability model: unresponsive hosts enter `UNCERTAIN_FIREWALLED` and require both consecutive-miss threshold and quarantine duration before release
- Subnet management with CIDR validation (max /24 per scan), IP matrix view, and per-subnet scan scheduling via in-process APScheduler
- IP provisioning API (`/ips/available`) for Terraform/automation integration
- Per-IP audit history with full state-transition timeline
- HTMX dashboard (server-rendered, no Node build step): CIDR matrix grid, IP inspector drawer, scan job monitor, settings, provision helper
- Dashboard authentication: API-key sessions plus optional LDAP/AD login with hardcoded group→role mapping (`netscan-admins`→admin, `netscan-operators`→operator)
- Session-cookie-authenticated proxy routes (`/web/*`) for all dashboard writes
- REST API with API-key auth (`X-API-Key`), three roles (admin/operator/read_only), and race-safe bootstrap endpoint
- Outbound webhooks: HMAC-SHA256 signed payloads, event subscription, exponential-backoff retries
- CLI: `netscan serve` (dashboard/API modes) and `netscan login` (LDAP → API key)
- Observability: structured logging (text/JSON), access-log middleware, monotonic scan durations
- Security hardening: SECRET_KEY enforcement, CORS allow-list, global rate limiting, webhook SSRF blocklist, trusted-proxy support
- Deployment: multi-stage Dockerfile (non-root, healthcheck), Alembic migrations on startup, SQLite WAL mode
- CI: GitHub Actions (pytest matrix 3.10/3.12, ruff lint+format, docker build + healthcheck) and GHCR image publishing on version tags

[Unreleased]: https://github.com/Salar-prog/netscan/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Salar-prog/netscan/releases/tag/v0.1.0
