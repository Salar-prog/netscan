> **ARCHIVAL NOTE** — Original hardening plan (Phases 1-5, 2026-08-24). All phases completed. For the current production-hardening plans, see `plan-hardening-p0-p1.md` and `plan-hardening-p2.md`. Kept for historical reference.

# NetScan Production Hardening Plan

**Goal**: Make netscan deployable on production and staging server networks.

---

## Phase 1: Fix Crash Bugs & Functional Breakage

**Scope**: Files that will crash or fail on first boot.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1.1 | `pyproject.toml` (new) | Missing entirely — `pip install -e .` fails | Create with all deps from README |
| 1.2 | `main.py:46-47` | `StaticFiles` mounts empty dir | Remove static mount (no static files exist) |
| 1.3 | `main.py:39` | `allow_origins=["*"]` + `allow_credentials=True` invalid per CORS spec | Read allowed origins from `Settings` (default `["*"]` for dev, lock down in prod) |
| 1.4 | `views.py:112-116` | Unknown IP in drawer creates phantom `IPAddress` with random `subnet_id` | Return 404 instead |
| 1.5 | `drawer.html:80` | `hx-patch` sends form-encoded, API expects JSON body | Add `hx-vals='{"is_reserved": ...}'` or switch to JS `fetch` with JSON |
| 1.6 | `provision.html:47` | `fetch()` to API has no auth header — fails when keys exist | Pass `X-API-Key` from a data attribute on the page |

**DoR**: All existing tests pass (after deps installed).
**DoD**: App starts with `uvicorn netscan.main:app`, all 6 HTMX forms functional, `pip install -e .` works.

---

## Phase 2: Security Hardening

**Scope**: Auth, secrets, CORS, CSRF, rate limiting.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 2.1 | `config.py:13` | Hardcoded `SECRET_KEY` default | Default to empty string; raise `ValueError` at startup if still empty and `DEBUG=False` |
| 2.2 | `config.py` | No `ALLOWED_ORIGINS` setting | Add `ALLOWED_ORIGINS: list[str] = ["*"]` — override in prod via env |
| 2.3 | `auth.py:30-33` | Open access when no keys exist | Remove open-access bootstrap; require API key always (first key created via CLI or direct DB) |
| 2.4 | `models.py:147` | Webhook secrets stored plaintext | Store HMAC hash only; return raw secret once at creation, never again |
| 2.5 | `api/v1/webhooks.py` | No input validation on webhook URL | Add `HttpUrl` validation on the Pydantic model |
| 2.6 | `main.py` | No rate limiting | Add `slowapi` or simple in-memory rate limiter to API routes |
| 2.7 | Templates | No CSRF tokens on HTMX forms | Generate CSRF token in `base.html`, include in all forms, validate on backend |
| 2.8 | `webhooks.py:18` | Webhook `secret` in `WebhookCreate` is plaintext | Auto-generate secret server-side; don't accept from client |

**DoR**: Phase 1 complete.
**DoD**: App rejects unauthenticated requests after first key created; webhook secrets hashed; CORS locked down; CSRF tokens on all forms.

---

## Phase 3: Package & Deploy Infrastructure

**Scope**: pyproject.toml, Alembic, Dockerfile, .gitignore, git hygiene.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 3.1 | `pyproject.toml` | Created in Phase 1 | Ensure complete: deps, scripts, optional deps |
| 3.2 | `alembic/` (new) | No migration support | Add Alembic with initial migration from SQLModel metadata |
| 3.3 | `Dockerfile` (new) | No container support | Multi-stage: Python 3.12, nmap, non-root user, healthcheck |
| 3.4 | `.gitignore` | Only covers `needle/` | Add `__pycache__/`, `*.pyc`, `.env`, `*.db`, `*.cact`, `.pytest_cache/`, `alembic/` generated |
| 3.5 | Git history | 29 `.pyc` files committed | `git rm --cached` all `.pyc` files |
| 3.6 | All source files | CRLF line endings uncommitted | Normalize to LF, commit |
| 3.7 | `alemb.ini` + `alembic/env.py` | New | Configure to use `DATABASE_URL` from settings |

**DoR**: Phase 2 complete.
**DoD**: `pip install -e .[test]` works; `alembic upgrade head` creates schema; `docker build .` succeeds; git working tree clean (no CRLF noise, no pyc).

---

## Phase 4: Health Check & Observability

**Scope**: Logging, health check, structured output.

| # | File | Issue | Fix |
|---|------|-------|-----|
| 4.1 | `main.py:54-56` | Health check is static JSON | Verify DB connectivity + nmap availability; return degraded status if unhealthy |
| 4.2 | `main.py:13` | Basic `logging.basicConfig` | Use `logging.config.dictConfig` with JSON formatter for prod |
| 4.3 | `scan_service.py` | No structured logging | Add JSON log fields: `subnet_cidr`, `scan_job_id`, `ips_found`, `duration_ms` |
| 4.4 | `scheduler_service.py` | No logging of job failures | Log scan failures with structured context |
| 4.5 | `webhook_service.py` | Silent failures on webhook dispatch | Log success/failure with HTTP status, retry count |

**DoR**: Phase 3 complete.
**DoD**: `/health` returns real status; logs are JSON-structured; scan/webhook failures are logged with context.

---

## Phase 5: Test Coverage Gaps

**Scope**: Untested modules, error paths, edge cases.

| # | File | Gap | Tests to add |
|---|------|-----|-------------|
| 5.1 | `services/scheduler_service.py` | Zero tests | Test job registration, removal, interval scheduling |
| 5.2 | `services/webhook_service.py` | Zero tests | Test HMAC signature generation, event filtering, retry logic |
| 5.3 | `services/scan_service.py` | Zero tests | Test scan execution (mock nmap), reconciliation, error handling |
| 5.4 | `scanner/runner.py` | 1 test (happy path XML) | Add: malformed XML, empty XML, nmap not found, timeout |
| 5.5 | `api/v1/ips.py` | No tests for PATCH/DELETE | Test reservation toggle, metadata update, history |
| 5.6 | `api/auth.py` | No role-based access tests | Test admin/operator/read_only permission enforcement |
| 5.7 | `classifier.py` | 5 tests (happy paths) | Add: reserved IP with active probe, edge cases (timezone-naive timestamps) |

**DoR**: Phase 4 complete.
**DoD**: All modules have at least basic test coverage; error paths tested; `pytest` passes with 0 failures.

---

## Execution Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
```

Each phase is independently deployable (except Phase 1 must come first). Phases 3-5 can be parallelized after Phase 2.

## Non-Goals (Explicitly Out of Scope)

- Needle SLM integration (Phase 2 in PLAN.md — deferred)
- PostgreSQL-specific optimizations (SQLite is fine for internal tool at this scale)
- IPv6 support (IPv4 only per PLAN.md)
- RBAC enforcement in API middleware (keys are stored but not enforced on routes — adding this is a larger change that should be a separate effort)
- Elasticsearch/Meilisearch for IP search (SQL LIKE is sufficient for internal use)
