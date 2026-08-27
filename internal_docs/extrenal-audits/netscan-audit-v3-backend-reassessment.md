# NetScan — Reassessment Round 3 (Backend Hardening)

Pulled `8d96c64..2785752` — 56 files, +2183/-258. This was a big round (P0/P1/P2 hardening passes). Two things worth flagging before the scorecard, because they change the picture more than the rest combined.

## First: something I missed in round 1 and 2, not just something they missed

Rate limiting was never actually enforced. `Limiter(default_limits=["120/minute"])` existed, `app.state.limiter` was set, the exception handler was registered — but `SlowAPIMiddleware` was never added to the app. Without that middleware, slowapi's `default_limits` don't apply to anything; they're inert unless a route has an explicit `@limiter.limit(...)` decorator, which none did. Every request I sent through this analysis for two rounds was hitting an effectively unlimited API. This round adds `app.add_middleware(SlowAPIMiddleware)` and it's genuinely fixed now — but I should have caught that it was dead configuration back when I first verified the trusted-proxy logic in round 1, instead of confirming the logic was correct without checking it was ever invoked. Flagging it plainly rather than quietly folding it in as if I'd caught it the first time.

## Second: one item is marked closed but isn't — with a concrete fix below

Commit `7ab4474` lists "F34 bootstrap kill-switch" alongside other fixes, which reads like the original bootstrap-key race (item #12, first audit) got resolved. It didn't. What actually shipped is a `DISABLE_BOOTSTRAP` setting — defaults to `False` — that lets an operator turn the bootstrap endpoint off *after* they're done using it. That's a reasonable, separate hardening step. But the actual race is untouched: `bootstrap_first_key` still does `existing = session.exec(select(ApiKey)).first()` then unconditionally creates and commits a new key, same as round 1. Two concurrent calls during initial setup — exactly the window that matters, since the endpoint has to be enabled for you to bootstrap anything in the first place — still both succeed and both mint an admin key.

**Suggested fix:** the check-then-insert pattern can't be made safe by checking harder; it needs something at the database level that physically can't let two inserts both win. The simplest version that works identically on SQLite and Postgres is a singleton lock row — a table with a fixed primary key that the bootstrap transaction claims as part of the same commit:

```python
# models.py
class BootstrapLock(SQLModel, table=True):
    __tablename__ = "bootstrap_lock"
    id: int = Field(default=1, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)
```

```python
# auth_keys.py — bootstrap_first_key
existing = session.exec(select(ApiKey)).first()   # keep as a fast-path, not the guarantee
if existing:
    raise NetScanException("BOOTSTRAP_DISABLED", "...", status_code=403)

raw_key, key_hash, prefix = generate_api_key()
api_key_rec = ApiKey(name=payload.name, key_hash=key_hash, prefix=prefix, role=Role.ADMIN, is_active=True)

session.add(BootstrapLock(id=1))   # this is what actually makes the race safe
session.add(api_key_rec)
try:
    session.commit()
except IntegrityError:
    session.rollback()
    raise NetScanException(
        "BOOTSTRAP_RACE",
        "Another request already completed bootstrap. Use POST /api/v1/auth/keys with a valid key.",
        status_code=409,
    )
```

`id=1` on `BootstrapLock` is the same value every time, so the second concurrent transaction's `INSERT` collides on the primary key and fails — deterministically, not probabilistically the way relying on `key_hash` uniqueness does. Needs one new Alembic migration to create the table. This is the same class of fix as the `IdempotencyRecord` fix below — a real uniqueness constraint doing the work, not a try/except wrapped around an operation that was never going to collide on its own.

---

## Everything else, verified against the actual diff

**✅ Cleanly fixed — no further action:**
- **SSRF** — `is_url_blocked()` moved into a shared `netscan/webhooks_check.py`, imported by both `api/v1/webhooks.py` and `web/views.py`. One implementation, both callers use it.
- **Concurrency guard** — `check_active_scan` now lives in and is called from `scan_service.py` itself (the shared execution layer), plus the API endpoint and the scheduler both call the same function.
- **LDAP injection** — `escape_filter_chars()` now wraps the username before it hits the search filter.
- **busy_timeout** — moved to a `@event.listens_for(engine, "connect")` hook, applied to every pooled connection. `init_db()` is now a no-op with schema fully owned by Alembic.
- **Orphaned job recovery** — `recover_stale_scan_jobs()` runs at startup, marks any `QUEUED`/`RUNNING` job older than 10 minutes as `FAILED`.
- **Rate limiting** — `SlowAPIMiddleware` added; see above.
- **CORS** — `ALLOWED_ORIGINS` default changed from `"*"` to `""`, resolving to an empty allow-list.
- **Webhook event_id** — every dispatched payload carries a `uuid.uuid4()` event ID.
- **Postgres in CI** — a real `test-postgres` job with an actual `postgres:16` service container.
- **Metrics endpoint** — `/metrics` hits the DB for real counts and emits real Prometheus text format.
- **Graceful shutdown (webhooks)** — in-flight webhook delivery tasks are tracked and drained before exit.

**⚠️ Partial — fix suggested below:**

- **Typed response models.** Meaningfully increased (subnets 1→5, ips and auth_keys both doubled), honestly scoped in the commit as "key routes" rather than claimed complete. `webhooks.py` is still at 1.

  **Suggested fix:** finish the pattern already used elsewhere — a typed `WebhookRead` on the remaining routes:
  ```python
  class WebhookRead(BaseModel):
      id: uuid.UUID
      name: str
      url: str
      events: list[str]
      is_active: bool
      created_at: datetime
      # secret deliberately excluded — it's only ever returned once, at creation

  @router.get("/webhooks", response_model=list[WebhookRead])
  @router.get("/webhooks/{webhook_id}", response_model=WebhookRead)
  ```
  Worth double-checking while you're in there: make sure `secret` genuinely never appears in any response after creation — that's the kind of thing a raw dict return can leak by accident that a typed model can't.

- **Idempotency keys.** Correct for the case that matters most — client times out, retries later, the second request finds the first's stored record and returns it. Has a narrower version of the bootstrap race: two *truly simultaneous* requests with the same key can both pass the "no existing record" check and both execute the underlying operation, and the second one's final `session.commit()` isn't wrapped in error handling — so instead of a clean deduplicated response, it surfaces as an unhandled 500.

  **Suggested fix:** the `idempotency_key` column is already `unique=True` — the fix is just to catch the collision instead of letting it propagate, then hand back the winner's stored response:
  ```python
  try:
      session.add(record)
      session.commit()
  except IntegrityError:
      session.rollback()
      winner = session.exec(
          select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == idempotency_key)
      ).first()
      return Response(
          content=json.dumps(winner.response_body, default=str),
          status_code=winner.status_code,
          media_type="application/json",
      )
  return Response(content=resp_body, status_code=response.status_code, ...)
  ```
  Same fix shape as the bootstrap lock: let the database's own uniqueness constraint be the arbiter, and handle the loser gracefully instead of assuming there won't be one.

- **Graceful shutdown (scans).** Webhook draining is real; an in-flight `nmap` subprocess itself isn't explicitly awaited or cancelled on shutdown. Self-heals within 10 minutes via the orphaned-job recovery on next startup, but that's a safety net, not a clean drain.

  **Suggested fix:** mirror the pattern already built for `_webhook_tasks`:
  ```python
  _scan_tasks: set[asyncio.Task] = set()

  # wherever a scan is kicked off:
  task = asyncio.create_task(scan_service.execute_scan(job_id))
  _scan_tasks.add(task)
  task.add_done_callback(_scan_tasks.discard)
  ```
  ```python
  # lifespan, after yield, alongside the webhook drain:
  if _scan_tasks:
      logger.info("Waiting for %d in-flight scan(s)...", len(_scan_tasks))
      await asyncio.wait(_scan_tasks, timeout=30)
  ```
  A bounded timeout matters here specifically — an `nmap` sweep can legitimately run longer than you want shutdown to block for, and anything still running when the timeout hits gets picked up by the recovery sweep on the next boot anyway, so it's a real drain for the common case without turning a deploy into a hang for the rare one.

**❌ Still open:**

- **Bootstrap-key race** — fix above.

- **Scheduler multi-instance.** Not fixed, and not silently ignored either: `39d2d9e` explicitly documents the single-instance constraint rather than claiming it's resolved. `AsyncIOScheduler()` still uses the default in-memory jobstore, so two replicas both independently fire every recurring scan on schedule.

  **Suggested fix, two versions depending on how much you want to invest right now:**

  *Quick, zero-new-infrastructure version* — matches the project's existing philosophy of not needing Redis/Celery. Add a flag and document that exactly one replica runs with it on:
  ```python
  # config.py
  SCHEDULER_ENABLED: bool = True
  ```
  ```python
  # lifespan
  if settings.SCHEDULER_ENABLED:
      scheduler.start()
  ```
  Operators running N replicas set `SCHEDULER_ENABLED=false` on all but one. Manual, but honest, immediate, and needs no new moving parts.

  *More robust version, worth it once you actually need elastic replicas* — pull recurring scheduling out of the app process entirely. Have an external trigger (cron, a k8s `CronJob`, whatever the deployer already has) call the existing scan-trigger endpoint on the desired interval, instead of the app timing itself. This has a nice side effect: because the concurrency guard now lives in `execute_scan` itself (the earlier fix), it's already safe even if the external trigger fires from more than one place or double-fires — the shared guard rejects the duplicate the same way it would today. Externalizing the *timing* gets you multi-replica safety for free from a fix you already have, without needing a distributed lock or a new dependency.

---

## Where this leaves it

This was a legitimately serious hardening pass — the SSRF and concurrency-guard fixes in particular were done the right way (shared layer, not another endpoint patch), which is exactly the correction the last two rounds were pointing at. Rate limiting going from decorative to enforced is a big, quiet win.

Priority order for what's left: **bootstrap lock row first** (small, self-contained, closes a real hole). **Idempotency error handling second** (same fix shape, five minutes of work once the pattern's fresh). **Scheduler flag third** (unblocks running >1 replica at all, even if the elastic version comes later). Typed response models and scan-task draining are polish at this point, not blockers — do them on the next pass through the API surface rather than as a dedicated round.
