> **ARCHIVAL NOTE** — P0+P1 hardening plan (2026-08-27). All stages completed and merged in PR #26. For the current state, see `progress.md`. Kept for historical reference.

# NetScan Production Hardening Plan — P0 + P1

**Created:** 2026-08-27
**Scope:** API-backend-only launch. Dashboard/CLI deferred.
**Sources:** internal_docs/extrenal-audits/netscan-api-backend-roadmap.md, internal_docs/extrenal-audits/netscan-audit-v2-reassessment.md, docs/PRODUCTION_READINESS.md

---

## Stage 1 — P0-1: Rate limiting enforcement

**Scope:**
- `netscan/config.py:19` — add `RATE_LIMIT_DEFAULT: str = "120/minute"`
- `netscan/limiter.py:19` — change hardcoded `"120/minute"` → `settings.RATE_LIMIT_DEFAULT`
- `netscan/main.py:134` — add `SlowAPIMiddleware` import + `app.add_middleware(SlowAPIMiddleware, ...)` after CORS middleware
- `tests/conftest.py:3` — add `os.environ.setdefault("RATE_LIMIT_DEFAULT", "10000/minute")` after `DEBUG=true`

**Inputs/dependencies:** None.
**Outputs:** Rate limiting actually enforced on all `/api/v1` endpoints. Tests suite doesn't 429 itself.
**Tier-1 test:** `tests/test_rate_limit.py` — build isolated app with `Limiter(default_limits=["2/minute"])` → 3rd request to `/api/v1/subnets` gets 429. Suite-wide high ceiling prevents flake.
**Non-goals:** Rate limit per-role, Redis-backed limiter storage, dashboard route limiting.

---

## Stage 2 — P0-4: busy_timeout per-connection

**Scope:**
- `netscan/db.py` — add `@event.listens_for(engine, "connect")` hook that executes `PRAGMA busy_timeout=5000` on every new SQLite connection
- `netscan/db.py:18-22` — remove the one-shot pragma block from `init_db()`

**Inputs/dependencies:** None.
**Outputs:** Every DB connection gets busy_timeout=5000, not just the startup connection.
**Tier-1 test:** `test_db.py` — connect to in-memory sqlite, execute `PRAGMA busy_timeout`, assert returns 5000.
**Non-goals:** Postgres compatibility (separate concern).

---

## Stage 3 — P0-2: Stale job recovery

**Scope:**
- `netscan/services/scan_service.py` — add `recover_stale_scan_jobs(session, max_age_seconds=600)` as module-level function. Selects QUEUED/RUNNING jobs where `created_at < utc_now() - timedelta(seconds=max_age_seconds)`, marks FAILED with `error_message="Recovered by startup: job stuck"`.
- `netscan/main.py:100` — call `recover_stale_scan_jobs(session)` in lifespan after `init_db()`, before `scheduler.start()`. Fresh `Session(engine)`.

**Inputs/dependencies:** None.
**Outputs:** Crashed/redeployed processes no longer leave permanent zombies.
**Tier-1 tests:**
- `test_scan_service.py` — seed RUNNING job with `created_at` 20 min ago → call `recover_stale_scan_jobs` → assert FAILED.
- Seed RUNNING job with `created_at` 1 min ago → assert unchanged.
**Non-goals:** Requeue logic (just mark FAILED, let next scheduled trigger handle it).

---

## Stage 4 — P0-3: Migrations in Docker + fatal failure

**Scope:**
- `Dockerfile:22` — add `COPY alembic.ini ./` and `COPY alembic/ ./alembic/` before `RUN useradd`
- `netscan/main.py:101-109` — remove `try/except` around alembic upgrade. Let exceptions propagate (lifespan fails, uvicorn stops).
- `tests/conftest.py:3` — add `os.environ.setdefault("DATABASE_URL", "sqlite://")` so lifespan migration targets in-memory DB.

**Inputs/dependencies:** None.
**Outputs:** Docker image contains migration files. Startup fails loudly on migration errors instead of silently serving an unversioned schema.
**Tier-1 test:** Docker build CI validates image builds. Unit test: mock `alembic_command.upgrade` to raise → assert exception propagates (no swallow).
**Non-goals:** Alembic auto-generation, Postgres migration testing.

---

## Stage 5 — P0-5: Concurrency guard in execute_scan

**Scope:**
- `netscan/services/scan_service.py` — add `check_active_scan(session, subnet_id) -> ScanJob | None`. In `execute_scan()`, call it after fetching job, before setting RUNNING. If active exists → mark current FAILED with `"Skipped: active scan exists on subnet"`.
- `netscan/api/v1/subnets.py:239-249` — replace inline guard with `from netscan.services.scan_service import check_active_scan`. Keep 409 HTTP response.
- `netscan/services/scheduler_service.py:78-88` — `trigger_scheduled_scan`: call `check_active_scan` before creating new job. If active → log skip, return early (no 409).

**Inputs/dependencies:** None.
**Outputs:** All scan creation paths (API + scheduler) go through the same guard. No concurrent scans on same subnet.
**Tier-1 tests:**
- `test_scan_service.py` — seed RUNNING job for subnet A → queue second job → execute → assert second job FAILED.
- `test_scheduler_service.py` — seed RUNNING job → trigger_scheduled_scan → assert no new ScanJob row.
**Non-goals:** Job priority, queue depth limits.

---

## Stage 6 — P1-6: Error envelope

**Scope:**
- `netscan/api/v1/router.py` — add `NetScanException` base class + handler that returns `{"error_code": "...", "message": "...", "details": {...}}`.
- Convert existing `HTTPException` raises in `subnets.py`, `webhooks.py`, `auth_keys.py` to use `NetScanException` where an error_code is useful. Keep HTTPException for simple 404s.

**Inputs/dependencies:** None.
**Outputs:** Machine-parseable error responses. Callers branch on `error_code`, not prose strings.
**Tier-1 test:** Trigger 409 duplicate scan → assert response has `error_code`, `message` keys. Trigger 400 bad CIDR → same.
**Non-goals:** Exhaustive error catalog, RFC 7807 compliance.

---

## Stage 7 — P1-7: Idempotency keys

**Scope:**
- `netscan/models.py` — add `IdempotencyRecord(SQLModel, table=True)` with `idempotency_key` (unique), `endpoint`, `response_body` (JSON), `status_code`, `request_hash`, `created_at`.
- `netscan/api/v1/router.py` — add `IdempotencyKeyMiddleware` that intercepts `Idempotency-Key` header on POST/PUT/PATCH/DELETE. Check DB → replay if found (key + endpoint + request body hash match). After successful response → store. TTL 24h, prune on access.
- `alembic/versions/` — new migration for `idempotency_records` table.

**Inputs/dependencies:** None.
**Outputs:** Retrying a mutating POST with the same key returns the same response, no duplicate side effects.
**Tier-1 test:** POST `/api/v1/subnets` with `Idempotency-Key: abc` → 201. Same key again → same response body, no new subnet.
**Non-goals:** Redis-backed idempotency store, background pruning job.

---

## Stage 8 — P1-8: Subnets pagination

**Scope:**
- `netscan/api/v1/subnets.py:36-85` — add `limit: int = Query(default=50, le=200)` and `offset: int = 0` to `list_subnets`. Apply `.offset(offset).limit(limit)` to the query.

**Inputs/dependencies:** None.
**Outputs:** Consistent pagination across all list endpoints.
**Tier-1 test:** Create 5 subnets → `?limit=2&offset=0` returns 2, `?limit=2&offset=2` returns 2, `?limit=10` returns 5.
**Non-goals:** Cursor-based pagination, total count in response.

---

## Stage 9 — P1-9: Webhook event_id

**Scope:**
- `netscan/services/webhook_service.py:37-41` — add `"event_id": str(uuid.uuid4())` to the payload dict.

**Inputs/dependencies:** None.
**Outputs:** Consumers can deduplicate at-least-once deliveries.
**Tier-1 test:** Mock httpx → dispatch event → assert captured request body contains `event_id` key.
**Non-goals:** Server-side dedup tracking, event log table.

---

## Stage 10 — P1-10: CORS lockdown

**Scope:**
- `netscan/config.py:27` — change `ALLOWED_ORIGINS: str = ""` (empty = no CORS headers).
- `netscan/main.py:134-140` — skip CORS middleware entirely when `ALLOWED_ORIGINS` is empty.

**Inputs/dependencies:** None.
**Outputs:** No CORS headers by default. Production must explicitly set `ALLOWED_ORIGINS`.
**Tier-1 test:** Default (empty) → no `access-control-allow-origin` header. Set to `https://example.com` → matching origin gets header.
**Non-goals:** Vary: Origin handling, wildcard with credentials.

---

## Regression & Gate Strategy

Each stage:
1. Implement within declared scope only
2. Write Tier-1 test
3. Run `pytest -v` (show real output)
4. Run `ruff check netscan/ tests/`
5. Commit (conventional commit referencing stage)
6. Move to next stage

After stages 1+2: push + watch CI.
After stage 5: push + watch CI.
After stage 10: push + watch CI.

## Explicit Exclusions

- F27 python-ldap packaging (stays Option B per prior decision)
- F11/F12 webhook reliability (P1/M, separate follow-up)
- F26 TOCTOU unique index on bootstrap (schema change, deferred)
- F16 probe-mode warning (cosmetic, P3)
- F17 dashboard count cap (dashboard deferred)
- F19 CSRF decision-log update (docs-only, deferred)
- Scheduler multi-replica jobstore (P3)
- /metrics endpoint (P3)
