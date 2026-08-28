# NetScan — Reassessment Round 4

Pulled `2785752..7bcda59` — one focused commit mapping directly to the four things suggested last round: bootstrap lock, idempotency race, scan drain, scheduler flag. Given how concurrency-sensitive two of those are, I didn't just read the code this time — I installed it in a clean virtualenv and actually ran the bootstrap flow against a genuinely fresh database. Good thing I did.

## The bootstrap lock fix breaks bootstrap entirely

Confirmed by actually running it, not just reading it. Fresh SQLite database, migrations applied, zero API keys, first-ever call to the bootstrap endpoint:

```
$ curl -X POST http://127.0.0.1:8123/api/v1/auth/keys/bootstrap -d '{"name":"first-admin-key"}'
{"error_code":"BOOTSTRAP_RACE","message":"Another request already completed bootstrap. Use POST /api/v1/auth/keys with a valid key.","details":{}}
```

Nobody has bootstrapped anything. This is the very first request. It fails anyway.

The cause: the new migration doesn't just create the `bootstrap_lock` table — it also inserts the singleton row as part of `upgrade()`:

```python
op.create_table("bootstrap_lock", ...)
op.execute("INSERT INTO bootstrap_lock (id) VALUES (1)")   # <- this is the bug
```

Since Alembic migrations run automatically on every startup (the round-3 fix), that row exists from the moment the app first boots — before anyone has ever called the endpoint. `bootstrap_first_key` then does `session.add(BootstrapLock(id=1))` to claim the lock, which is supposed to succeed for the *first* caller and only fail for a second, racing one. But the row's already there, seeded by the migration, so the very first legitimate call collides with a row that was never supposed to exist yet. Every call — first, second, hundredth — hits the same `IntegrityError` branch and returns 409. There is currently no way to create an API key on a fresh install through this endpoint at all.

**Fix:** the table needs to start empty. Whoever inserts the row first should be whoever actually calls bootstrap, not the migration:

```python
def upgrade() -> None:
    op.create_table(
        "bootstrap_lock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # no seed insert — the first successful bootstrap call claims row id=1
```

This needs a second migration, not just an edit to this one — anything that's already run `b3c4d5e6f7a8` (which, given auto-migration-on-startup, is anything that's deployed this commit at all, including whatever you're running right now) already has the poisoned row sitting in its database. The follow-up migration needs to actually delete it:

```python
def upgrade() -> None:
    op.execute("DELETE FROM bootstrap_lock WHERE id = 1")
```

so existing deployments get unstuck, not just future ones.

## Scan draining doesn't cover scheduler-triggered scans — and it's worse than just "not covered"

`_scan_tasks` tracking was added at the two manual trigger points (`subnets.py`'s API endpoint, `views.py`'s dashboard proxy), each doing `_scan_tasks.add(task)` / `task.add_done_callback(_track_scan_task)` right after creating the task. `scheduler_service.py`'s `trigger_scheduled_scan` was never touched — it just does `await scan_service.execute_scan(scan_job_id)` directly, inside a coroutine that APScheduler itself invokes. There's no task object for the app to add to the tracking set, because the app never created one — APScheduler did, internally.

That's the same shape of gap as the SSRF and concurrency-guard issues from earlier rounds: a fix landed at the call sites the person was looking at, and a different call site doing the same underlying thing was out of view. I flagged this exact category of mistake last round and it's back, just attached to a new piece of functionality.

It's actually worse than just "unprotected," though — I checked empirically rather than assuming `scheduler.shutdown()` provides its own implicit safety net. It doesn't:

```
[T+0.00s] slow_job STARTED
[T+1.00s] calling scheduler.shutdown() now (default wait=True)...
[T+1.00s] scheduler.shutdown() RETURNED after 0.00s
Job raised an exception: asyncio.exceptions.CancelledError
```

APScheduler's `AsyncIOScheduler.shutdown()` documents `wait=True` as the default — "wait for currently executing jobs to finish" — but for coroutine jobs specifically (as opposed to thread-pool-executed sync jobs), that's not what actually happens: the job gets cancelled immediately, `CancelledError` and all. And in `main.py`, `scheduler.shutdown()` is called *before* the `_scan_tasks` drain block. So a scan that's running because the scheduler kicked it off gets hard-cancelled the moment shutdown begins — before the new draining logic even runs, and it wouldn't have mattered anyway since that scan was never in `_scan_tasks` to begin with.

**Fix, and it's the same lesson as the concurrency guard fix that *was* done right:** put the registration inside `execute_scan` itself, not at each caller. It can self-register using `asyncio.current_task()`, so it doesn't matter whether the task was created by `subnets.py`, `views.py`, or invoked directly by APScheduler:

```python
# scan_service.py
async def execute_scan(self, scan_job_id: uuid.UUID) -> None:
    task = asyncio.current_task()
    if task is not None:
        _scan_tasks.add(task)
        task.add_done_callback(_scan_tasks.discard)
    ...
```

That closes the tracking gap for all three callers at once, no caller-side changes needed, and removes the two now-redundant `_scan_tasks.add(...)` calls in `subnets.py`/`views.py`.

That alone doesn't fix the cancellation problem, though — `scheduler.shutdown()` still runs first and still cancels whatever's in flight before the drain block gets a chance. The ordering needs to flip: drain `_scan_tasks` *before* calling `scheduler.shutdown()`, not after. And since `wait=True` doesn't actually do anything useful here, it's worth being explicit about that rather than relying on a default that doesn't hold for this executor type — call `scheduler.shutdown(wait=False)` and let the app's own `_scan_tasks` drain be the one mechanism that actually waits, instead of having two shutdown paths that don't coordinate with each other.

---

## The other two, verified working

**Idempotency race** — correctly fixed. The final `session.commit()` is now wrapped in `try/except IntegrityError`, and on conflict it fetches and returns the winning record's stored response instead of letting the loser 500:
```python
except IntegrityError:
    session.rollback()
    winner = session.exec(select(IdempotencyRecord).where(...)).first()
    if winner:
        return Response(content=json.dumps(winner.response_body, ...), status_code=winner.status_code, ...)
```
Worth knowing as a limitation rather than a bug: the underlying operation (`call_next(request)`) still runs twice if two requests with the same key arrive genuinely simultaneously — this fix makes the *response* the caller sees clean and deduplicated either way, it doesn't prevent the side effect itself from executing twice on that narrow timing. That's a smaller, harder-to-hit gap than the bootstrap one (needs true concurrency, not just "someone retries later"), and probably not worth chasing further unless it shows up in practice.

**Scheduler flag** — correctly wired. `SCHEDULER_ENABLED` defaults to `True`, gates both `scheduler.start()` and `scheduler.shutdown()` with a plain if/else, nothing concurrent or racy about it. Does what it says.

---

## Where this leaves it

The bootstrap issue is the most serious thing found across all four rounds of this — not because it's a subtle security gap, but because it's a complete functional break of the one flow every new install depends on. It needs to go out before anything else here, including as a hotfix ahead of whatever else is in flight, since it's currently sitting live on the deployed branch. The scan-draining gap is real but lower urgency — it only bites during a redeploy that happens to land mid-scheduled-scan, and the orphaned-job recovery from round 3 means it self-heals within ten minutes even when it does happen.
