# Changes Log

Every actual change made, mapped to the stage that produced it.

---

## Phase 1: Crash Bugs & Functional Breakage

### Stage 1.1 -- Project scaffolding
- Created `pyproject.toml` with all dependencies (fastapi, uvicorn, sqlmodel, pydantic-settings, apscheduler, httpx, jinja2, python-multipart, slowapi, alembic)
- Created `tests/conftest.py` with shared `client` and `auth_client` fixtures
- Updated `.gitignore` for `__pycache__/`, `*.pyc`, `.env`, `*.db`, `.pytest_cache/`, `*.egg-info/`

### Stage 1.2 -- Remove dead StaticFiles mount
- `netscan/main.py`: Removed `StaticFiles` import and `app.mount("/static", ...)` block

### Stage 1.3 -- Fix CORS
- `netscan/main.py`: Changed `allow_origins=["*"]` to `[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]`

### Stage 1.4 -- Fix drawer 404
- `netscan/web/views.py`: Drawer route returns 404 for unknown IPs instead of creating phantom IPAddress

### Stage 1.5 -- Fix drawer form submission
- `netscan/web/templates/drawer.html`: Switched from `hx-patch` with form-encoded to JS `fetch()` with JSON body

### Stage 1.6 -- Fix provision page
- `netscan/web/views.py`: Added `/web/ips/available` server-side endpoint
- `netscan/web/templates/provision.html`: Updated to use server-side endpoint instead of direct API call (avoids auth issue)

### Stage 1.7 -- Test infrastructure
- `tests/conftest.py`: Shared `client` fixture (in-memory SQLite, dependency override), `auth_client` fixture (bootstraps API key)
- `tests/test_api.py`: Rewritten to use shared `auth_client` fixture
- `tests/test_web.py`: Rewritten to use shared `client` fixture

### Stage 1.8 -- Git hygiene
- Removed 29 `.pyc` files from git tracking (`git rm --cached`)
- Updated `.gitignore` to prevent future commits

### Stage 1.9 -- Line endings
- Normalized all tracked `.py` and `.html` files from CRLF to LF

---

## Phase 2: Security Hardening

### Stage 2.1 -- SECRET_KEY validation
- `netscan/config.py`: Added `validate_for_production()` method, called at app lifespan startup

### Stage 2.2 -- ALLOWED_ORIGINS setting
- `netscan/config.py`: Added `ALLOWED_ORIGINS: str = "*"` field

### Stage 2.3 -- Remove open-access bootstrap
- `netscan/api/auth.py`: `get_current_api_key()` now always requires a valid key (no special case for empty DB)

### Stage 2.4 -- Webhook URL validation
- `netscan/api/v1/webhooks.py`: `WebhookCreate.url` changed from `str` to `AnyHttpUrl`

### Stage 2.5 -- Webhook secret hidden
- `netscan/api/v1/webhooks.py`: Added `WebhookResponse` model (no secret field); `GET /webhooks` uses `response_model=List[WebhookResponse]`; `POST /webhooks` returns secret once in response body

### Stage 2.6 -- Rate limiting
- Created `netscan/limiter.py`: Shared `Limiter(key_func=get_remote_address, default_limits=["120/minute"])`
- `netscan/main.py`: Wired slowapi exception handler, added `@limiter.exempt` to `/health`

### Stage 2.7 -- Webhook auto-generation
- `netscan/api/v1/webhooks.py`: Secret generated via `secrets.token_urlsafe(32)`, not accepted from client

### Stage 2.8 -- Classifier type fix
- `netscan/scanner/classifier.py`: Changed `event_details: Dict[str, Any] = None` to `Optional[Dict[str, Any]] = None`

### Stage 2.9 -- Settings template cleanup
- `netscan/web/templates/settings.html`: Removed stale "Signing Secret" input from webhook modal, fixed "open setup mode" text

---

## Phase 3: Deploy Infrastructure

### Stage 3.1 -- Alembic setup
- Created `alembic.ini`: Placeholder `sqlalchemy.url` (overridden by env.py)
- Created `alembic/env.py`: SQLModel metadata import, `Settings().DATABASE_URL`, `render_as_batch=True`

### Stage 3.2 -- Initial migration
- Created `alembic/versions/e04c2d38a789_initial_schema.py`: Creates subnets, ip_addresses, scan_jobs, ip_history, webhooks, api_keys tables

### Stage 3.3 -- Dockerfile
- Created `Dockerfile`: Python 3.12-slim, nmap, non-root `netscan` user, `chown -R netscan:netscan /app`, healthcheck

### Stage 3.4 -- .dockerignore
- Created `.dockerignore`: Excludes .git, tests, .env, *.db, __pycache__, .pytest_cache, *.egg-info, needle/

---

## Post-Phase Fixes

### Fix: pyproject.toml missing deps
- `pyproject.toml`: Added `slowapi>=0.1.9` and `alembic>=1.13.0` (were imported but not declared)

### Fix: Dockerfile non-root user can't write DB
- `Dockerfile`: Added `chown -R netscan:netscan /app` before `USER netscan`

---

## Phase 5: Test Coverage Gaps

### PR #2 (feat/phase5-test-coverage)

- `tests/test_auth_roles.py`: 5 tests for role-based access control (read_only, operator, admin, revoked key, key hash hiding)
- `tests/test_scan_service.py`: 4 tests for scan orchestration (success, missing subnet, scanner failure, state-change audit)
- `tests/test_scheduler_service.py`: 6 tests for scheduler logic (schedule/skip/remove subnets, trigger scan)
- `tests/test_webhook_service.py`: 6 tests for webhook dispatch (HMAC signature, event filtering, wildcard subscriptions, retry/give-up)
- `tests/test_scanner.py`: 14 tests for nmap XML parsing, reason-to-method mapping, build_nmap_args branches
- `tests/test_classifier.py`: 11 tests for edge cases (unseen hosts, miss/quarantine independence, recovery paths)

Additional fixes:
- **fix:** `netscan/api/v1/subnets.py`: scan trigger endpoint made async (was sync but used `asyncio.create_task`)
- **fix:** `netscan/services/scan_service.py`: capture `subnet.cidr` and `job.subnet_id` inside session to avoid DetachedInstanceError

---

## Phase 6: Observability

### Stage 6.1 -- Structured logging config
- `netscan/config.py`: Added `LOG_FORMAT` and `LOG_LEVEL` settings
- `netscan/main.py`: Replaced `logging.basicConfig` with `logging.config.dictConfig`; added `JSONFormatter` class; added `AccessLogMiddleware`

### Stage 6.2 -- Scan service logging
- `netscan/services/scan_service.py`: Added structured logging for scan started, scan completed (with duration_ms), scan failed (with error)

### Stage 6.3 -- Webhook dispatch logging
- `netscan/services/webhook_service.py`: Added structured logging for webhook delivered (status_code, duration_ms) and webhook delivery failed (error, attempt, duration_ms)

### Stage 6.4 -- Access logging middleware
- `netscan/main.py`: Added `AccessLogMiddleware` ASGI middleware logging method, path, status_code, duration_ms, client_ip; exempt `/health`; log level based on status code

### Stage 6.5 -- Scheduler failure logging
- `netscan/services/scheduler_service.py`: Added structured logging for scheduler started (job_count), job registration/removal, wrapped `trigger_scheduled_scan` in try/except with error logging

### Post-merge fix
- `netscan/services/scan_service.py`: Switched from `datetime.now(timezone.utc)` to `time.monotonic()` for scan duration measurement (SQLite returns naive datetimes, causing subtraction with aware datetime to fail)
- `netscan/services/scan_service.py`: Removed duplicate `logger.exception` line left from merge

---

## Phase 7: CI/CD

### Stage 7.1 -- Ruff config
- `pyproject.toml`: Added `[tool.ruff]` section with `line-length = 120`, `target-version = "py310"`, `select = ["E", "F", "W"]`

### Stage 7.2 -- GitHub Actions workflow
- `.github/workflows/ci.yml`: 3 parallel jobs triggered on push to main and PRs:
  - `test`: Python 3.10 + 3.12 matrix, `pytest -v`
  - `lint`: `ruff check` + `ruff format --check`
  - `docker`: Build image, start container, hit `/health`

### Stage 7.3 -- Fix lint violations
- Removed unused imports across 10 files (F401)
- Fixed boolean comparisons: `Column.is_active == True` → `Column.is_active` in auth.py, scheduler_service.py, webhook_service.py (E712)
- Fixed line-length violations in subnets.py, scan_service.py, scheduler_service.py, webhook_service.py, views.py (E501)
- Fixed trailing whitespace in views.py (W293)
- Auto-formatted all files with `ruff format`

---

## Phase 8: Modular UI Web-Dashboard (PLANNED)

No changes yet. This phase will break the monolithic web dashboard into
domain-specific modules and add export functionality.
