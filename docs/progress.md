# Progress Log

Live status of implementation phases.

---

## Phase 1: Fix Crash Bugs & Functional Breakage

**Status:** COMPLETE
**Commit:** `9fb1c20`

| Item | Status | Notes |
|------|--------|-------|
| 1.1 Create pyproject.toml | Done | All deps, editable install works |
| 1.2 Remove dead StaticFiles mount | Done | No more 404 on /static |
| 1.3 Fix CORS (ALLOWED_ORIGINS from Settings) | Done | No more hardcoded wildcard |
| 1.4 Fix drawer 404 bug | Done | Returns 404, no phantom IP creation |
| 1.5 Fix drawer HTMX form | Done | Switched to JS fetch with JSON body |
| 1.6 Fix provision page | Done | Server-side /web/ips/available endpoint |
| 1.7 Test infrastructure | Done | conftest.py with shared fixtures |
| 1.8 Remove .pyc from git | Done | 29 files removed, .gitignore updated |
| 1.9 Normalize CRLF to LF | Done | All source files normalized |

---

## Phase 2: Security Hardening

**Status:** COMPLETE
**Commit:** `e62041d`

| Item | Status | Notes |
|------|--------|-------|
| 2.1 SECRET_KEY validation | Done | ValueError at startup if empty + DEBUG=False |
| 2.2 ALLOWED_ORIGINS from Settings | Done | Comma-separated string |
| 2.3 Remove open-access bootstrap | Done | API key required on all endpoints |
| 2.4 Webhook URL validation | Done | AnyHttpUrl on Pydantic model |
| 2.5 Webhook secret hidden after creation | Done | WebhookResponse model, no secret field |
| 2.6 Rate limiting | Done | slowapi, 120/min global, /health exempt |
| 2.7 Webhook secret auto-generation | Done | secrets.token_urlsafe(32), returned once |
| 2.8 CSRF | SKIPPED | N/A -- no session cookies, header-only auth |

---

## Phase 3: Deploy Infrastructure

**Status:** COMPLETE
**Commit:** `0362188`

| Item | Status | Notes |
|------|--------|-------|
| 3.1 Alembic init | Done | SQLModel metadata + Settings integration |
| 3.2 Initial migration | Done | Creates all 6 tables |
| 3.3 Dockerfile | Done | Python 3.12-slim, nmap, non-root user, healthcheck |
| 3.4 .dockerignore | Done | Excludes .git, tests, .env, *.db |

---

## Phase 4: Health Check & Observability

**Status:** COMPLETE (merged into Phase 6)

| Item | Status | Notes |
|------|--------|-------|
| 4.1 Health check with real status | Done | Verifies DB + nmap, returns degraded if unhealthy |
| 4.2 JSON structured logging | Done | Implemented in Phase 6 |
| 4.3 Scan service structured logging | Done | Implemented in Phase 6 |
| 4.4 Scheduler failure logging | Done | Implemented in Phase 6 |
| 4.5 Webhook dispatch logging | Done | Implemented in Phase 6 |

---

## Phase 5: Test Coverage Gaps

**Status:** COMPLETE
**PR:** #2 (feat/phase5-test-coverage, merged to main)

| Item | Status | Notes |
|------|--------|-------|
| 5.1 scheduler_service tests | Done | 6 tests: job add/skip/remove logic, trigger_scheduled_scan |
| 5.2 webhook_service tests | Done | 6 tests: HMAC signature, event filter, wildcard, retry/give-up |
| 5.3 scan_service tests | Done | 4 tests: success path, missing subnet, scanner failure, state-change audit |
| 5.4 runner.py edge cases | Done | 14 tests: XML edge cases, reason->method mapping, build_nmap_args branches |
| 5.5 ips.py PATCH/DELETE tests | Done (PATCH only) | No DELETE endpoint exists on /ips; PATCH + history covered |
| 5.6 auth.py role-based tests | Done | Role enforcement implemented (require_role); admin-only key mgmt, operator writes |
| 5.7 classifier.py edge cases | Done | 11 total: unseen hosts, miss/quarantine independence, recovery paths |

Additional fixes made while writing tests:

- **fix:** scan trigger endpoint was sync but used `asyncio.create_task` -- crashed with "no running event loop". Made async.
- **fix:** scan_service accessed detached ORM attributes (`subnet.cidr`, `job.subnet_id`) after session close -- DetachedInstanceError with default expire_on_commit. Fields now captured inside session.

---

## Phase 6: Observability

**Status:** COMPLETE
**PR:** #3 (feat/observability, merged to main)

| Item | Status | Notes |
|------|--------|-------|
| 6.1 Structured logging config | Done | LOG_FORMAT + LOG_LEVEL settings, JSONFormatter, dictConfig |
| 6.2 Scan service logging | Done | Log start/end/failure with subnet_cidr, duration_ms |
| 6.3 Webhook dispatch logging | Done | Log delivery success/failure with webhook_name, status_code, duration_ms |
| 6.4 Access logging middleware | Done | ASGI middleware logging method, path, status_code, duration_ms, client_ip |
| 6.5 Scheduler failure logging | Done | Log job registration/removal, try/except on trigger_scheduled_scan |

Post-merge fix: switched scan duration measurement from `datetime.now(timezone.utc)` to `time.monotonic()` to avoid SQLite naive/aware datetime mismatch.

---

## Phase 7: CI/CD

**Status:** COMPLETE
**PR:** #4 (feat/ci-cd, merged to main)

| Item | Status | Notes |
|------|--------|-------|
| 7.1 Ruff config | Done | Added to pyproject.toml: E/F/W rules, line-length 120, target py310 |
| 7.2 GitHub Actions workflow | Done | 3 parallel jobs: test (Python 3.10+3.12), lint (ruff), docker (build+health) |
| 7.3 Fix lint violations | Done | Unused imports, boolean comparisons, line length, formatting |

---

## Phase 8: Modular UI Web-Dashboard (PLANNED)

**Status:** DEFERRED

| Item | Status | Notes |
|------|--------|-------|
| 8.1 Modular dashboard architecture | Deferred | Deferred to focus on Phase 10 (LDAP + dashboard fixes) |
| 8.2 CSV/JSON export | Deferred | Deferred |
| 8.3 Dashboard polish | Deferred | Deferred |
| 8.4 RBAC route enforcement | Deferred | Deferred |

---

## Phase 9: Production-Readiness Audit

**Status:** COMPLETE
**Commit:** `8995d2e` through `6f7c047`

| Item | Status | Notes |
|------|--------|-------|
| 9.1 Max CIDR prefix /24 | Done | `netscan/scanner/cidr.py`, `netscan/config.py` — rejects /23, /16, /8 |
| 9.2 Scan concurrency guard | Done | `netscan/api/v1/subnets.py` — 409 on duplicate RUNNING/QUEUED job |
| 9.3 SQLite WAL + busy timeout | Done | `netscan/db.py` — WAL mode enabled on startup, 5s busy timeout |
| 9.4 Webhook exponential backoff | Done | `netscan/services/webhook_service.py` — 1s, 2s, 4s between retries |
| 9.5 Trusted proxy support | Done | `netscan/config.py`, `netscan/limiter.py` — `TRUSTED_PROXIES` env var |
| 9.6 Multi-stage Docker build | Done | `Dockerfile` — builder + runtime stages |
| 9.7 Alembic on startup | Done | `netscan/main.py` — `alembic upgrade head` at lifespan |
| 9.8 SSRF blocklist | Done | `netscan/config.py`, `netscan/api/v1/webhooks.py` — RFC1918, link-local, metadata blocked |
| 9.9 Bootstrap race-safe | Done | `netscan/api/v1/auth_keys.py` — IntegrityError catch |
| 9.10 Pin Docker base image | Done | `Dockerfile` — `python:3.12.8-slim` |
| 9.11 Dependency lockfile | Done | `requirements-lock.txt` |
| 9.12 scan_cidr integration tests | Done | `tests/test_scanner.py` — 4 new tests |
| 9.13 E2E audit tests | Done | `tests/test_e2e_audit_fixes.py` — 9 tests covering all audit fixes |
| 9.14 Docker capabilities documented | Done | `README.md` — NET_RAW, NET_ADMIN documented |

---

## Phase 10: LDAP/AD Authentication & Dashboard Proxy Routes (PLANNED)

**Status:** NOT STARTED

Phase 10 addresses two critical production blockers:
1. **Dashboard HTMX forms are broken** — all write operations (create subnet, trigger scan, manage keys/webhooks, reserve IPs) POST to `/api/v1/*` endpoints that require `X-API-Key` header, but the dashboard only has session cookies. Every action returns 401.
2. **No enterprise authentication** — the dashboard only supports API key login. For production deployment in corporate environments, LDAP/AD integration is required so users authenticate with their existing corporate credentials.

### Stage 10.1 — Config & Dependencies
**Files:** `netscan/config.py`, `pyproject.toml`

Add LDAP settings to `Settings`:
- `LDAP_ENABLED` (bool, default False)
- `LDAP_SERVER_URI` (str, e.g. `ldap://dc01.corp.local`)
- `LDAP_BIND_DN` (str, service account DN)
- `LDAP_BIND_PASSWORD` (str, service account password)
- `LDAP_USER_SEARCH_BASE` (str, OU containing users)
- `LDAP_USER_SEARCH_FILTER` (str, default `(sAMAccountName={username})`)
- `LDAP_GROUP_SEARCH_BASE` (str, OU containing groups)
- `LDAP_GROUP_SEARCH_FILTER` (str, default `(member={user_dn})`)
- `LDAP_START_TLS` (bool, default False)
- `LDAP_CA_CERT_FILE` (str, optional CA cert path)

Add `python-ldap>=3.4.0` to `pyproject.toml`.

| Item | Status | Notes |
|------|--------|-------|
| 10.1 Config & dependencies | Planned | LDAP settings in config.py, python-ldap in pyproject.toml |

### Stage 10.2 — LDAP Auth Module
**Files:** `netscan/auth/__init__.py` (new), `netscan/auth/ldap.py` (new)

Create `netscan/auth/` package with two functions:
- `ldap_authenticate(username, password)` → binds to LDAP, returns `{username, dn, groups}` or `None`
- `map_groups_to_role(groups)` → hardcoded mapping: `netscan-admins`→ADMIN, `netscan-operators`→OPERATOR, else READ_ONLY

| Item | Status | Notes |
|------|--------|-------|
| 10.2 LDAP auth module | Planned | netscan/auth/ldap.py with bind + group→role mapping |

### Stage 10.3 — Session Cookie Dual Format
**Files:** `netscan/web/session.py`

Extend session cookie to support both auth types:
- API key session: `ak:{key_hash}:{timestamp}:{sig}` (current behavior)
- LDAP session: `ldap:{username}:{role}:{timestamp}:{sig}` (new)

Updated `validate_session_cookie()` returns `{"type": "ak"|"ldap", ...}`.

| Item | Status | Notes |
|------|--------|-------|
| 10.3 Session cookie dual format | Planned | ak: and ldap: cookie formats, backward compatible |

### Stage 10.4 — Dashboard Login with LDAP
**Files:** `netscan/web/views.py`, `netscan/web/templates/login.html`

Update login flow:
- Login form shows username/password fields when LDAP enabled
- Falls back to API key field when LDAP disabled
- LDAP login creates session cookie with username + group-derived role

| Item | Status | Notes |
|------|--------|-------|
| 10.4 Dashboard login with LDAP | Planned | Login page supports both LDAP and API key auth |

### Stage 10.5 — Dashboard Proxy Routes
**Files:** `netscan/web/views.py`

Add server-side proxy routes under `/web/*` that accept session cookie auth:

| Route | Method | Proxied To |
|-------|--------|-----------|
| `POST /web/subnets` | POST | create_subnet() |
| `POST /web/subnets/{id}/scan` | POST | trigger_subnet_scan() |
| `POST /web/auth/keys` | POST | create_api_key() |
| `DELETE /web/auth/keys/{id}` | DELETE | revoke_key() |
| `POST /web/webhooks` | POST | create_webhook() |
| `DELETE /web/webhooks/{id}` | DELETE | delete_webhook() |
| `POST /web/webhooks/{id}/test` | POST | test_webhook() |
| `PATCH /web/ips/{ip}` | PATCH | update_ip_reservation() |

Each proxy route checks session cookie + role permission before calling the service function.

| Item | Status | Notes |
|------|--------|-------|
| 10.5 Dashboard proxy routes | Planned | 8 /web/* routes fixing all broken HTMX forms |

### Stage 10.6 — Update Templates
**Files:** `netscan/web/templates/*.html`

Update all HTMX forms to target `/web/*` routes:
- `index.html`: subnet creation, scan trigger
- `matrix.html`: scan trigger
- `settings.html`: key generation, revoke, webhook CRUD
- `drawer.html`: IP reservation form

| Item | Status | Notes |
|------|--------|-------|
| 10.6 Update templates | Planned | All HTMX targets changed from /api/v1/* to /web/* |

### Stage 10.7 — CLI LDAP Login
**Files:** `netscan/cli.py`

Add `netscan login` command:
- Prompts for username + password (masked input)
- Binds to LDAP, on success creates API key with mapped role
- Prints API key for user to save

| Item | Status | Notes |
|------|--------|-------|
| 10.7 CLI LDAP login | Planned | `netscan login` authenticates via LDAP, returns API key |

### Stage 10.8 — Tests
**Files:** `tests/test_ldap.py` (new), `tests/test_web.py` (update), `tests/conftest.py` (update)

11+ new tests covering LDAP auth, group mapping, session cookie formats, proxy routes, and dashboard integration.

| Item | Status | Notes |
|------|--------|-------|
| 10.8 Tests | Planned | Mock LDAP tests, proxy route tests, dual cookie tests |

### Stage 10.9 — Documentation
**Files:** `README.md`, `AGENTS.md`, `docs/*.md`, `docs/qa-dashboard-testing.md`

Update all docs with Phase 10 info, LDAP config, and QA test plan.

| Item | Status | Notes |
|------|--------|-------|
| 10.9 Documentation | Planned | README, AGENTS, progress, changes, decisions, learnings, QA guide |

---

## Summary

| Phase | Status | Tests |
|-------|--------|-------|
| Phase 1 | COMPLETE | 19/19 pass |
| Phase 2 | COMPLETE | 19/19 pass |
| Phase 3 | COMPLETE | 19/19 pass |
| Phase 4 | COMPLETE | (merged into Phase 6) |
| Phase 5 | COMPLETE | 65/65 pass |
| Phase 6 | COMPLETE | 65/65 pass |
| Phase 7 | COMPLETE | 65/65 pass |
| Phase 8 | DEFERRED | — |
| Phase 9 | COMPLETE | 93/93 pass |
| Phase 10 | IN PROGRESS (10.4) | — |
