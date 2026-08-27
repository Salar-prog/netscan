> **ARCHIVAL NOTE** — API backend roadmap (2026-08-25). Most Tier 0 and Tier 1 items are now completed. Kept for historical reference.

# NetScan as an API Backend for Other Tools/Automations — Roadmap

The bar changes more than it first looks. A human clicking a dashboard tolerates a stuck job, an occasional 500, a UI that needs a refresh. A backend other systems call in a pipeline doesn't get that tolerance — it needs to be **idempotent, recoverable, and predictable** even when the caller is a cron job or another service with no human watching. That reframes which of the existing gaps matter most, and surfaces a few new ones the dashboard use case never exercised.

One pattern shows up three separate times below — worth naming once instead of three times: **a fix keeps getting added at the call site instead of the shared layer underneath it.** The webhook SSRF blocklist lives in one API route, not the model or dispatcher, so a second route creating webhooks skips it. The concurrent-scan guard lives in the manual API endpoint, not `execute_scan` or the scheduler. As you harden this for automation consumers, the fix is almost always "move the invariant down a layer" rather than "add another endpoint-level check."

---

## Tier 0 — Carried over, still blocking regardless of framing

These don't go away just because the consumer is a machine instead of a browser:
- Webhook SSRF blocklist only checked in `/api/v1/webhooks`, not the dashboard's `/web/webhooks` — fix by moving `_is_url_blocked()` into the `Webhook` model's validation or the dispatcher, so every creation path goes through it once.
- Bootstrap-key race — needs an actual DB-level singleton (a lock row with a fixed PK, or a `SELECT ... FOR UPDATE`-style guard), not a try/except around an insert that was never going to collide.
- `busy_timeout` needs a `@event.listens_for(engine, "connect")` hook so it applies to every pooled connection, not just the one used at startup.

---

## Tier 1 — Specific to "other systems depend on this"

**1. The concurrency guard doesn't cover the automation path.**
`trigger_subnet_scan` (the API) checks for an active job first. `execute_scan` and `trigger_scheduled_scan` (the scheduler) don't. If a subnet's scan interval is shorter than a scan actually takes, recurring automated scans stack concurrently — the exact bug #2 was supposed to kill, just reachable through the scheduler instead of the API. **Move the check into `execute_scan` itself** so every caller inherits it for free.

**2. No recovery for interrupted jobs.**
Nothing on startup reconciles `ScanJob` rows stuck in `RUNNING` from a previous process that crashed or was redeployed mid-scan. Combine that with the concurrency guard, and a single crash **permanently wedges scanning on that subnet** — every future trigger sees the zombie `RUNNING` row and returns 409, forever, until someone manually fixes the database. For a backend other systems poll and retry against, this is the difference between "self-healing" and "needs a human to notice and intervene." Add a startup sweep: any `RUNNING` job older than its own timeout window gets marked `FAILED` (or requeued) before the app starts accepting traffic.

**3. No graceful shutdown.**
`lifespan()` calls `scheduler.shutdown()` on exit but doesn't drain or account for scans already in flight. Paired with #2, every deploy is a small chance of an orphaned job. At minimum, track in-flight scan tasks and either wait for them (bounded) or mark them explicitly interrupted on SIGTERM, instead of just letting the process die under them.

**4. The scheduler can't run more than one replica.**
`AsyncIOScheduler()` uses the default in-memory job store. Run two instances for uptime — which you'll want, once other systems depend on this being up — and **both** independently fire every recurring scan on schedule: duplicate scans, duplicate `ScanJob` rows, duplicate webhook events landing on whatever's consuming them downstream. Either move to a persistent/shared job store (APScheduler supports a SQLAlchemy jobstore, which you already have a DB connection for), or pull scheduling out of the app process entirely and have an external trigger (cron, k8s CronJob) call the existing manual-trigger endpoint instead.

**5. API contract isn't actually stable yet.**
`response_model` is used on a handful of routes; most return raw dicts. For a UI that's fine — a human reads whatever comes back. For automations building against this, the response shape isn't a documented contract, it's whatever the current dict literal happens to contain, and it can change without anyone noticing in the OpenAPI schema. Put a typed Pydantic response model on every route before calling the API "stable" — this is also what makes client SDK generation (OpenAPI → typed client) actually reliable for whoever's building the automation.

**6. No idempotency keys on mutating endpoints.**
The scan-trigger endpoint is accidentally idempotent now (409 on a duplicate). Subnet creation and webhook creation aren't — an automation that times out waiting for a response and retries the same `POST` will create a second subnet or a second webhook with the same intent. Standard fix: accept an `Idempotency-Key` header, store a short-lived record of key → response, and replay the stored response on a repeat key instead of re-executing.

**7. Pagination is inconsistent.**
IPs listing has `limit`/`offset` with a sane cap. Subnets listing doesn't appear to. An automation enumerating subnets at scale will eventually get a response that just keeps growing. Make every list endpoint paginate the same way, with the same parameter names — an automation shouldn't need special-case logic per endpoint.

**8. CORS is wide open by default, and you probably don't need it at all here.**
`ALLOWED_ORIGINS` defaults to `"*"` combined with `allow_credentials=True`. Browsers won't literally send `*` with credentials, so Starlette reflects the actual request origin back instead — which in practice means **any website can make credentialed requests** against this API by default. For server-to-server automation clients, there's no browser in the loop at all, so CORS is close to irrelevant — the fix here is easy: lock `ALLOWED_ORIGINS` down to just whatever origins the dashboard itself is served from (or drop the middleware entirely if the dashboard ends up split out), rather than trying to tune it for a use case that doesn't need it.

**9. Errors aren't machine-parseable.**
FastAPI's default `{"detail": "..."}` is fine for a human reading a browser error. An automation branching on failure needs a stable error *code*, not a prose string it has to pattern-match. Add a consistent error envelope (`{"error_code": "SCAN_ALREADY_RUNNING", "message": "...", "details": {...}}`) so callers can switch on `error_code` instead of parsing English sentences.

**10. Webhook delivery is at-least-once with no documented dedup story.**
The signature and a timestamp are already in the payload — good foundation. But nothing enforces a replay window server-side, and there's no unique event ID in the payload for a consumer to dedupe on if a webhook fires twice (which will happen — that's what "at-least-once" means in practice once retries exist). Add an `event_id` (UUID) to every payload and document that consumers should dedupe on it; document the timestamp tolerance you expect consumers to enforce rather than leaving it implicit.

**11. SQLite is a real ceiling here, not just a tuning problem.**
WAL mode helps a single instance survive concurrent readers plus one writer. It doesn't give you a second application instance sharing the database safely at any real write volume, and "backend other tools depend on" is exactly the scenario where you eventually want more than one instance. `DATABASE_URL` suggests Postgres is a supported swap — but CI only runs against SQLite; there's no Postgres job in the matrix. Before recommending Postgres as the production path, actually add it to CI and run the full suite against it — the JSON column (`custom_metadata`) and UUID handling are the two places SQLite and Postgres are most likely to disagree silently.

**12. No metrics, no correlation ID.**
Structured logging exists, which is good. What's missing is a `/metrics` endpoint (even basic Prometheus counters: scans triggered/completed/failed, webhook delivery success/failure, request latency by route) and a correlation ID that follows a request from "automation calls the API" through "scan runs" through "webhook fires" through the logs. When something breaks in a pipeline three systems deep, "grep the logs for this UUID across all three services" is the difference between a five-minute fix and a afternoon of guessing.

---

## Suggested order

Roughly in the sequence I'd actually do this, since a few items block or simplify others:

1. Move the concurrency guard into `execute_scan` (#1) and add the orphaned-job sweep (#2) — these two together are what make the thing self-healing, which matters more than anything else once nobody's watching a dashboard.
2. Fix the SSRF and bootstrap-race carryovers (Tier 0) — small, well-understood, no reason to leave them.
3. Typed response models + consistent pagination + error envelope (#5, #7, #9) — one pass through the API surface, tedious but mechanical, and it's the actual contract other people's code will be written against.
4. Idempotency keys (#6) and webhook event IDs (#10) — needed the moment a real automation starts retrying against this.
5. Lock down CORS (#8) — quick, low-risk.
6. Postgres in CI, then recommend it for production (#11) — bigger lift, do it once the above is stable so you're not testing a moving target.
7. Scheduler jobstore or externalize scheduling (#4) and add metrics/correlation IDs (#12) — these matter once you're actually running more than one instance, which is the point where "backend for automations" stops being aspirational.
