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

**Status:** PARTIALLY COMPLETE

| Item | Status | Notes |
|------|--------|-------|
| 4.1 Health check with real status | Done | Verifies DB + nmap, returns degraded if unhealthy |
| 4.2 JSON structured logging | PENDING | Current: plain text basicConfig |
| 4.3 Scan service structured logging | PENDING | Missing: subnet_cidr, scan_job_id, duration_ms |
| 4.4 Scheduler failure logging | PENDING | Scan failures not logged |
| 4.5 Webhook dispatch logging | PENDING | Success/failure/retry not logged |

---

## Phase 5: Test Coverage Gaps

**Status:** NOT STARTED

| Item | Status | Notes |
|------|--------|-------|
| 5.1 scheduler_service tests | PENDING | Zero tests |
| 5.2 webhook_service tests | PENDING | Zero tests |
| 5.3 scan_service tests | PENDING | Zero tests |
| 5.4 runner.py edge cases | PENDING | 1 test (happy path only) |
| 5.5 ips.py PATCH/DELETE tests | PENDING | No tests |
| 5.6 auth.py role-based tests | PENDING | No tests |
| 5.7 classifier.py edge cases | PENDING | 5 happy-path tests |

---

## Phase 6: Observability (feat/observability branch)

**Status:** COMPLETE
**Branch:** `feat/observability`
**Commits:** 5 stages, all on feature branch

| Item | Status | Notes |
|------|--------|-------|
| 6.1 Structured logging config | Done | LOG_FORMAT + LOG_LEVEL settings, JSONFormatter, dictConfig |
| 6.2 Scan service logging | Done | Log start/end/failure with subnet_cidr, duration_ms |
| 6.3 Webhook dispatch logging | Done | Log delivery success/failure with webhook_name, status_code, duration_ms |
| 6.4 Access logging middleware | Done | ASGI middleware logging method, path, status_code, duration_ms, client_ip |
| 6.5 Scheduler failure logging | Done | Log job registration/removal, try/except on trigger_scheduled_scan |

---

## Summary

| Phase | Status | Tests |
|-------|--------|-------|
| Phase 1 | COMPLETE | 19/19 pass |
| Phase 2 | COMPLETE | 19/19 pass |
| Phase 3 | COMPLETE | 19/19 pass |
| Phase 4 | COMPLETE (merged into Phase 6) | 19/19 pass |
| Phase 5 | NOT STARTED | 19/19 pass |
| Phase 6 | COMPLETE (feature branch) | 19/19 pass |
