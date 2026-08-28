# Learnings

Gotchas, false starts, and things that didn't work and why.

---

## .pyc files committed to git

**Problem:** 29 `.pyc` files were committed in the initial commit. Python generates these in `__pycache__/` directories and they should never be tracked.

**Fix:** `git rm --cached` all `.pyc` files, added `__pycache__/` and `*.pyc` to `.gitignore`.

**Lesson:** Always set up `.gitignore` before the first commit.

---

## CRLF line endings

**Problem:** All source files had CRLF line endings (Windows-style). On Linux, this causes subtle issues with shebangs, shell scripts, and diff noise.

**Fix:** Normalized all tracked files to LF. Added `*.py` and `*.html` to a normalization pass.

**Lesson:** Normalize line endings at project creation, not after 10 commits.

---

## Missing pyproject.toml

**Problem:** The original repo had no `pyproject.toml`. `pip install -e .` failed immediately.

**Fix:** Created `pyproject.toml` with all dependencies from the README.

**Lesson:** Create `pyproject.toml` as the first file in any Python project.

---

## slowapi and alembic not declared as dependencies

**Problem:** `pyproject.toml` was created in Phase 1 without `slowapi` or `alembic`. Phase 2 added imports for slowapi, Phase 3 for alembic. The code imported them but they weren't declared as dependencies.

**Fix:** Added `slowapi>=0.1.9` and `alembic>=1.13.0` to `pyproject.toml` dependencies.

**Lesson:** When adding imports across phases, update `pyproject.toml` in the same commit.

---

## Dockerfile: non-root user can't write to /app

**Problem:** The Dockerfile created a `netscan` user but `/app` was owned by root. SQLite tried to create `netscan.db` in `/app` and failed with `OperationalError: unable to open database file`.

**Fix:** Added `chown -R netscan:netscan /app` before `USER netscan`.

**Lesson:** Non-root containers need explicit ownership of their working directory.

---

## SQLite database persisted between test runs

**Problem:** Running the app locally created `netscan.db` on disk. Subsequent test runs or re-bootstrapping hit stale data (bootstrap endpoint returned 403 because a key already existed).

**Fix:** `rm -f netscan.db` before testing. Test fixtures use in-memory SQLite (`sqlite://`).

**Lesson:** Tests must use isolated databases. For local testing, clean up the `.db` file.

---

## provision.html: HTMX form without auth

**Problem:** The provision page had a `fetch()` call to the API but no `X-API-Key` header. Once bootstrap was removed, the provision page broke.

**Fix:** Created a server-side `/web/ips/available` endpoint that the template calls instead. Avoids exposing API keys to the frontend.

**Lesson:** Web UI routes that call API endpoints need either server-side proxies or auth token injection.

---

## drawer.html: hx-patch sends form-encoded, API expects JSON

**Problem:** HTMX's `hx-patch` sends form-encoded data by default. The PATCH endpoint expected JSON.

**Fix:** Switched to JS `fetch()` with `Content-Type: application/json` body.

**Lesson:** HTMX form methods default to form-encoded. JSON APIs need explicit `hx-vals` or JS fetch.

---

## Bootstrap endpoint: first key must be bootstrapped

**Problem:** After removing open-access (Phase 2.3), there was no way to create the first API key. Every endpoint required an existing key.

**Fix:** Added `POST /api/v1/auth/keys/bootstrap` -- no auth required, auto-assigns ADMIN role, disabled after first use.

**Lesson:** When removing open access, always provide a bootstrap path. Don't leave a chicken-and-egg problem.

---

## Webhook secret can't be hashed

**Problem:** Original plan suggested hashing webhook secrets (like API keys). But the webhook dispatcher needs the raw secret to compute HMAC-SHA256 signatures for outbound payloads.

**Fix:** Store plaintext, return once at creation, hide from list endpoint.

**Lesson:** Before hashing any secret, check if it needs to be used for signing/verification.

---

## Timezone-aware/naive datetime mismatch with SQLite

**Problem:** `scan_service.py` used `scan_start = datetime.now(timezone.utc)` (timezone-aware) for duration measurement. When `job.completed_at` was set to `datetime.now(timezone.utc)` and read back from SQLite, it came back as a naive datetime (no timezone info). Subtracting aware from naive raises `TypeError: can't subtract offset-naive and offset-aware datetimes`.

**Fix:** Switched to `time.monotonic()` for duration measurement. `scan_start = time.monotonic()`, then `duration_ms = int((time.monotonic() - scan_start) * 1000)`. The `started_at` and `completed_at` fields still use `datetime.now(timezone.utc)` for display, but duration is measured with monotonic clock.

**Lesson:** SQLite doesn't preserve timezone info. Never use datetime arithmetic for durations across session boundaries — use `time.monotonic()` instead.

---

## Ruff format vs manual line wrapping

**Problem:** After fixing ruff E501 (line too long) violations by manually breaking lines, `ruff format --check` still failed because the formatter wanted different line breaks (e.g., dict literals, function calls, list comprehensions).

**Fix:** Ran `ruff format netscan/` to let the formatter handle all line wrapping. Manual line breaks were fighting the formatter's rules. Let the tool do it.

**Lesson:** Don't manually fix line-length violations if you're using ruff format. Fix the logical structure first (unused imports, boolean comparisons), then let `ruff format` handle the whitespace. Run `ruff format --check` last.

---

## HTMX forms broken after adding session auth

**Problem:** After implementing dashboard session cookie auth (`/login`, `/logout`, `netscan_session` cookie), all dashboard write operations returned 401. The HTMX forms POST to `/api/v1/*` endpoints which require `X-API-Key` header — but the browser only sends session cookies, not API key headers.

**Root cause:** Session auth and API key auth are separate systems. The dashboard templates were written to call API endpoints directly, which works when the user has an API key injected into the page (the original plan). Once session cookies replaced that, the API endpoints still expected headers.

**Fix (planned Phase 10.5):** Server-side proxy routes at `/web/*` that check session cookie auth, then call the same service functions. HTMX forms target `/web/*` instead of `/api/v1/*`.

**Lesson:** When adding a new auth mechanism, trace every write path end-to-end. The dashboard had 8 broken write operations that weren't caught until manual testing because the test fixtures only tested read routes.

---

## Bootstrap endpoint race condition

**Problem:** Two concurrent requests to `/api/v1/auth/keys/bootstrap` both checked "no keys exist" and both tried to create the first key. One succeeded, the other raised `IntegrityError` (unique constraint on key_hash).

**Fix:** Wrap bootstrap in `try/except IntegrityError` — if it fails due to race, return 403 (key already exists).

**Lesson:** Bootstrap endpoints with "create if empty" logic are inherently racy. Always catch the constraint violation.

---

## E2E test IP seeding issue

**Problem:** `test_full_lifecycle` in `test_e2e_audit_fixes.py` called `create_ip_address()` to seed IPs, but the function returned 422 (validation error). The subnet didn't exist in the test DB.

**Fix:** Seed the subnet first via `client.post("/api/v1/subnets", ...)`, then create IPs. Or use the `subnet_factory` fixture.

**Lesson:** E2E tests that chain operations need to set up prerequisites. The subnet must exist before IPs can be created under it.

---

## python-ldap can't be installed in every dev/CI environment

**Problem:** `netscan/auth/ldap.py` had `import ldap` at module level. `python-ldap` needs system packages (`libldap2-dev`, `libsasl2-dev`) to build, which aren't available in all environments (no sudo, restricted CI). Any test importing the module — even just `map_groups_to_role()`, which doesn't touch LDAP — crashed with `ModuleNotFoundError`.

**Fix:** Moved `import ldap` inside `ldap_authenticate()` with a try/except that logs and returns `None`. The module now imports cleanly everywhere; only actual LDAP authentication requires the library.

**Lesson:** Keep C-extension imports lazy in optional-integration modules. The pure-Python parts (mapping, config) should work without the system dependency, and the integration point should fail gracefully with a clear log message.

---

## Optional dependency: lazy import for testability

**Problem:** `netscan/auth/ldap.py` did `import ldap` at module level. When `python-ldap` isn't installed (test environment, CI without libldap2-dev), the entire module fails to import — breaking `map_groups_to_role()` which doesn't need ldap at all.

**Fix:** Moved `import ldap` inside `ldap_authenticate()` as a lazy import. Module loads fine without `python-ldap`; only the actual LDAP function fails gracefully with a logged error.

**Lesson:** For optional system-level dependencies (especially C extensions like python-ldap), keep the import lazy. Pure functions in the same module remain testable without the dependency installed.

---

## Test fixture for dual database support

**Problem:** conftest.py used `StaticPool` (SQLite-only) for all test runs. Adding a Postgres CI job meant the test fixture had to work with both SQLite and Postgres.

**Fix:** Detect `DATABASE_URL` env var. If SQLite, use `StaticPool` (in-memory, fast). If Postgres, use a regular engine (real connection to the CI service container). The `client_fixture` calls `_make_engine()` which returns the appropriate engine.

**Lesson:** When adding database driver support, update test infrastructure first — it's the fastest way to catch dialect incompatibilities.

---

## Zombie process reaping

**Problem:** `runner.py` called `process.kill()` on timeout but didn't `await process.wait()`. The process became a zombie until GC collected it — a brief leak.

**Fix:** Added `await process.wait()` after `process.kill()`. The process is properly reaped immediately.

**Lesson:** After killing a subprocess, always `await process.wait()` to reap it. CPython's GC will eventually collect it, but the window is a real (if brief) resource leak.

---

## Test assertion for new model fields

**Problem:** Adding `expires_at` and `revoked_at` to `ApiKeyResponse` broke `test_list_keys_does_not_expose_key_hash` — the test asserted an exact set of response keys.

**Fix:** Updated the assertion to include the new fields. Tests that assert exact response shapes are brittle under schema evolution — prefer checking "key not in response" (for secret fields) over "exactly these keys" (for non-secret fields).

**Lesson:** When adding response model fields, grep for exact-set assertions in tests. The `key_hash not in key` assertion was correct; the `set(keys[0].keys()) == {...}` assertion was the one that broke.

---

## Migration seed rows poison bootstrap

**Problem:** A migration created a `bootstrap_lock` table and seeded it with `INSERT INTO bootstrap_lock (id) VALUES (1)`. Since Alembic migrations run on every startup, the row existed before anyone called bootstrap. The bootstrap endpoint tried to insert the same row → `IntegrityError` → every bootstrap call returned 409 on fresh installs.

**Fix:** Remove the seed INSERT from the migration. The table starts empty; the first bootstrap call claims the row. A follow-up migration deletes the poisoned row for existing deployments.

**Lesson:** Migrations that seed data create implicit state that persists across restarts. If the seed row is meant to be claimed by application logic, the migration must not pre-create it — the application must be the first writer.

---

## SQLite-specific SQL in Alembic migrations

**Problem:** Migration used `server_default=sa.text("(datetime('now'))")` which is SQLite syntax. On Postgres, this failed with `function datetime(unknown) does not exist`.

**Fix:** Use `sa.func.now()` which generates dialect-appropriate SQL (SQLite: `datetime('now')`, Postgres: `now()`).

**Lesson:** Alembic migrations run against whatever database the app uses. Always use SQLAlchemy's portable functions (`sa.func.now()`, `sa.func.current_timestamp()`) instead of raw SQL dialects.

---

## APScheduler cancels coroutine jobs on shutdown

**Problem:** `scheduler.shutdown(wait=True)` is documented as "wait for currently executing jobs to finish" — but for coroutine jobs (not thread-pool sync jobs), it cancels them immediately with `CancelledError`. In-flight scans were killed before the drain block could run.

**Fix:** Call `scheduler.shutdown(wait=False)` and drain scan tasks before calling it. The app's own `_scan_tasks` drain is the mechanism that actually waits; `wait=True` is misleading for coroutine executors.

**Lesson:** APScheduler's `wait=True` only works for thread-pool jobs. For coroutine jobs, `shutdown()` cancels them. Don't rely on `wait=True` as a drain mechanism for async jobs — handle it yourself.

---

## Scan task tracking must be self-registering

**Problem:** Tracking in-flight scan tasks at the call site (`_scan_tasks.add(task)` in `subnets.py` and `views.py`) missed the scheduler path. APScheduler calls `execute_scan` directly without creating an `asyncio.Task` that the app can intercept.

**Fix:** Self-register inside `execute_scan` via `asyncio.current_task()`. Covers all callers (API, dashboard, scheduler) at once. No caller-side changes needed.

**Lesson:** When tracking async work for graceful shutdown, register inside the work itself, not at each caller. Callers are easily missed; the work function is always the same.
