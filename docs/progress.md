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
