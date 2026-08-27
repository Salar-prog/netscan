> **ARCHIVAL NOTE** — P2 hardening plan (2026-08-27). All stages completed and merged in PR #27. Many P3 items listed as non-goals are now completed (F19-F34). For the current state, see `progress.md`. Kept for historical reference.

# NetScan Production Hardening Plan — P2

**Created:** 2026-08-27
**Scope:** API-backend-only. 8 stages covering 11 open P2 findings from the production audit.
**Predecessor:** P0+P1 hardening (PR #26, merged). F9 (CORS default) already fixed.
**Sources:** docs/PRODUCTION_READINESS.md, internal_docs/extrenal-audits/netscan-audit-v2-reassessment.md, internal_docs/extrenal-audits/netscan-api-backend-roadmap.md

---

## Stage 1 — F5: Shared SSRF validation for all webhook creation paths

**Scope:**
- Extract `_is_url_blocked()` from `netscan/api/v1/webhooks.py:18-47` into a new shared module `netscan/webhooks_check.py` (or keep it in `webhooks.py` and import from there).
- `netscan/web/views.py:520-535` (`web_create_webhook`) — import and call the shared function before creating the `Webhook` row. Raise `HTTPException(400)` on blocked URL.
- Keep the existing call site in `netscan/api/v1/webhooks.py:91` working unchanged.
- Both paths (API + dashboard) now share one validation function.

**Inputs/dependencies:** None.
**Outputs:** Dashboard-created webhooks are SSRF-protected. Single source of truth.
**Tier-1 tests:**
- Create webhook via API with `http://169.254.169.254/meta` → assert 400 + `SSRF_BLOCKED` error code (existing).
- Create webhook via dashboard proxy route (`POST /web/webhooks`) with same URL → assert 400.
- Create webhook with `https://example.com` → assert success on both paths.
**Non-goals:** DNS resolution caching, fail-closed on DNS errors (P3 backlog item).

---

## Stage 2 — F6+F7: LDAP injection fix + async event-loop safety

**Scope:**
- `netscan/auth/ldap.py:48` — escape username before filter interpolation:
  ```python
  from ldap.filter import escape_filter_chars
  safe_username = escape_filter_chars(username)
  search_filter = settings.LDAP_USER_SEARCH_FILTER.format(username=safe_username)
  ```
- `netscan/auth/ldap.py:37-89` — wrap entire LDAP I/O block in `await asyncio.to_thread(_ldap_auth_sync, username, password)` so the sync `ldap.initialize()`, `search_s()`, `simple_bind_s()` calls don't block the event loop.
- Add `ldap.OPT_NETWORK_TIMEOUT` (e.g. 10 seconds) on the connection object to prevent indefinite hangs on unreachable DCs.
- `netscan/web/views.py:100` — the `login_post` handler that calls `ldap_authenticate` is already sync; after this change it calls the async wrapper, so it must become `async def` and `await` the result.

**Inputs/dependencies:** None.
**Outputs:** LDAP injection prevented. Event loop stays responsive during LDAP I/O. Timeout prevents indefinite freeze.
**Tier-1 tests:**
- Mock `ldap.initialize` + `search_s` → call `ldap_authenticate("admin)(|(cn=*", "pass")` → assert the filter sent to `search_s` contains escaped characters (literal `*` not treated as wildcard).
- Mock `ldap.initialize` to sleep 30s → call with `OPT_NETWORK_TIMEOUT=10` → assert it returns `None` within ~10s (not hanging).
**Non-goals:** Async python-ldap wrapper library, LDAP connection pooling.

---

## Stage 3 — F8: Secure cookie flag

**Scope:**
- `netscan/web/views.py:111` — add `secure=not settings.DEBUG` to `set_cookie` call.
- `netscan/web/views.py:132` — same fix on the second `set_cookie` call.

**Inputs/dependencies:** None.
**Outputs:** Session cookies include `Secure` flag in production (`DEBUG=false`). Sent only over HTTPS.
**Tier-1 tests:**
- Login with `DEBUG=false` → assert `Set-Cookie` header contains `Secure`.
- Login with `DEBUG=true` → assert `Set-Cookie` header does NOT contain `Secure`.
**Non-goals:** HSTS headers, cookie encryption.

---

## Stage 4 — F10: Throttle last_used_at writes

**Scope:**
- `netscan/api/auth.py:58-62` — instead of unconditional `key_rec.last_used_at = utc_now()` + commit on every request, only update if the last update was >1 hour ago:
  ```python
  now = utc_now()
  if not key_rec.last_used_at or (now - key_rec.last_used_at).total_seconds() > 3600:
      key_rec.last_used_at = now
      session.commit()
  ```
- This eliminates per-GET write amplification while keeping `last_used_at` reasonably fresh.

**Inputs/dependencies:** None.
**Outputs:** GET requests no longer trigger a DB write (except once per hour per key). Write amplification eliminated.
**Tier-1 tests:**
- Authenticate 3 rapid requests → assert only 1 commit (the first one sets `last_used_at`).
- Authenticate again after >1 hour (mock `utc_now`) → assert second commit happens.
**Non-goals:** Batched writes, Redis-backed throttle, removing `last_used_at` entirely.

---

## Stage 5 — F11+F12: Webhook task tracking + targeted test dispatch

**Scope:**
- `netscan/services/scan_service.py:266-270` — store `asyncio.create_task()` return values in a module-level set with done-callbacks that log exceptions and remove from the set:
  ```python
  _webhook_tasks: set[asyncio.Task] = set()

  def _track_task(task: asyncio.Task) -> None:
      _webhook_tasks.discard(task)
      if task.exception():
          logger.error("Webhook task failed", extra={"error": str(task.exception())})

  task = asyncio.create_task(...)
  task.add_done_callback(_track_task)
  _webhook_tasks.add(task)
  ```
- Apply same pattern to `netscan/api/v1/subnets.py:260`.
- `netscan/services/webhook_service.py:26-31` — add a new `dispatch_event_to()` classmethod that takes a specific `Webhook` object instead of querying all:
  ```python
  @classmethod
  async def dispatch_event_to(cls, event_name, data, webhook, session):
      # Same logic as dispatch_event but for a single webhook
  ```
- `netscan/api/v1/webhooks.py:135-152` (`test_webhook`) — use `dispatch_event_to()` with the specific `wh` instead of `dispatch_event()` which broadcasts.
- `netscan/web/views.py:554-570` (`web_test_webhook`) — same fix.

**Inputs/dependencies:** None.
**Outputs:** Webhook tasks are tracked and exceptions visible. Test endpoint delivers to exactly the targeted webhook. No more broadcast on test.
**Tier-1 tests:**
- Seed webhook subscribed to `["scan.completed"]` only → dispatch `webhook.test` via test endpoint → assert the webhook received it (mock httpx).
- Seed two webhooks, one subscribed to `scan.completed` one to `ip.state_changed` → test endpoint on webhook A → assert only A received the test, B did not.
- Mock `dispatch_event` to raise → assert the done-callback logs the error (no silent swallow).
**Non-goals:** Outbox pattern (B10 backlog), at-least-once delivery guarantee, task cancellation on shutdown.

---

## Stage 6 — F16+F17: Scanner warning + dashboard count cap

**Scope:**
- `netscan/scanner/runner.py:41-43` — after `self.is_privileged = self._detect_raw_socket_privileges()`, log a WARNING when unprivileged:
  ```python
  if not self.is_privileged:
      logger.warning("Scanner running unprivileged: ARP/SYN/ICMP probes disabled, using TCP-connect only")
  ```
- `netscan/web/views.py:332` — add `le=50` to `count` parameter:
  ```python
  count: int = Query(default=1, le=50)
  ```
  Also add `Query` import if missing.

**Inputs/dependencies:** None.
**Outputs:** Operators see a clear warning at startup when running without raw socket caps. Dashboard can't request unbounded IP lists.
**Tier-1 tests:**
- Instantiate `NmapScanner` with `geteuid=1000` and failed raw socket → assert WARNING in log output.
- Call `/web/ips/available?count=100` → assert 422 validation error.
- Call `/web/ips/available?count=5` → assert 200.
**Non-goals:** Runtime capability escalation, dynamic cap configuration.

---

## Stage 7 — F27: python-ldap as optional dependency

**Scope:**
- `pyproject.toml:39` — move `"python-ldap>=3.4.0"` from `dependencies` to a new optional group:
  ```toml
  [project.optional-dependencies]
  ldap = ["python-ldap>=3.4.0"]
  test = [...]
  ```
- `netscan/auth/ldap.py:30-33` — keep the existing `try: import ldap / except ImportError` guard (already handles missing package gracefully).
- `README.md` — update install instructions: `pip install -e ".[ldap]"` for LDAP support, `pip install -e ".[test,ldap]"` for dev with LDAP.
- `CONTRIBUTING.md` — same update.
- `Dockerfile` — add `pip install -e ".[ldap]"` in the builder stage (already has libldap-dev).
- `.github/workflows/ci.yml` — test jobs install `pip install -e ".[test,ldap]"` (already has `apt install libldap2-dev`).
- `netscan/cli.py:2` — guard the `netscan login` command to check if `ldap` is installed and print a helpful error if not.

**Inputs/dependencies:** None.
**Outputs:** Installing netscan without LDAP no longer requires gcc/libldap-dev. LDAP users opt in with `.[ldap]`.
**Tier-1 tests:**
- `pip install -e ".[test]"` (without ldap) → `import netscan` succeeds → `netscan serve` works.
- Mock `import ldap` to raise `ImportError` → call `ldap_authenticate()` → assert returns `None` with helpful log message.
**Non-goals:** Switching to `ldap3` (pure Python), making LDAP a fully separate package.

---

## Stage 8 — F26: Unique partial index for scan concurrency

**Scope:**
- `netscan/models.py` — add a `UniqueConstraint` on `ScanJob`:
  ```python
  from sqlalchemy import UniqueConstraint

  class ScanJob(SQLModel, table=True):
      ...
      __table_args__ = (
          UniqueConstraint("subnet_id", name="uq_active_scan_per_subnet"),
      )
  ```
  NOTE: A partial index (`WHERE status IN ('QUEUED','RUNNING')`) would be ideal but SQLModel/SQLite has limited partial index support via SQLAlchemy `Index` with `postgresql_where` / `sqlite_where`. Use a simpler approach: keep the application-level guard (already in `check_active_scan()`) and add a unique constraint on `(subnet_id, status)` where status is not terminal — OR rely on the existing application guard since SQLite doesn't support partial unique indexes via SQLModel cleanly.

  **Revised approach:** Since the application-level `check_active_scan()` guard already exists and works correctly for the single-instance case, and SQLite doesn't support partial unique indexes through SQLModel easily, skip the schema change and instead add a comment documenting why the application guard is sufficient (single-instance constraint). This is honest rather than adding a constraint that doesn't actually prevent the TOCTOU window.

- `netscan/services/scan_service.py` — add a comment at `check_active_scan()` documenting the TOCTOU limitation and that the single-instance constraint (documented in README/PRODUCTION_READINESS) makes it acceptable.

**Inputs/dependencies:** None.
**Outputs:** TOCTOU race documented as accepted risk under single-instance constraint. No false sense of security from a constraint that doesn't fully solve it.
**Tier-1 tests:** No new tests needed — existing `check_active_scan()` tests cover the happy path.
**Non-goals:** PostgreSQL partial indexes (unlocked by B9 Postgres CI), distributed locking.

---

## Regression & Gate Strategy

Each stage:
1. Implement within declared scope only
2. Write Tier-1 tests
3. Run `pytest -v` (show real output)
4. Run `ruff check netscan/`
5. Commit (conventional commit referencing stage)
6. Move to next stage

After stages 2, 5, 7: push + watch CI.

## Explicit Non-Goals (deferred to P3/backlog)

- F19 CSRF decision doc update (P3)
- F20 API-key rotation/expiry (B6 backlog)
- F21 Global IP lookups (P3)
- F22 Proxy-blind access logs (P3)
- F23 Scheduler-blind health check (P3)
- F24 Prometheus metrics (B8 backlog)
- F25 Single-instance docs (P3)
- F28 Singleton re-export (P3)
- F29 Version duplication (P3)
- F30 Reserved IP consecutive_misses (P3)
- F31 Zombie process on timeout (P3)
- F32 Dashboard fake progress (P3)
- F33 Redirect hack (P3)
- B10 Outbox pattern
- B9 Postgres in CI
- B11 CSV/JSON export
