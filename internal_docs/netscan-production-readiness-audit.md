> **ARCHIVAL NOTE** — Original production-readiness audit (2026-08-25, before Phase 9/10 hardening). Most findings are now addressed. For the current state, see `docs/PRODUCTION_READINESS.md`. Kept for historical reference.

# NetScan — Production-Readiness Audit

Scope: cloned `Salar-prog/netscan` and read the actual source (not just the README) — `netscan/scanner/`, `netscan/api/`, `netscan/services/`, `netscan/web/`, `netscan/db.py`, `netscan/config.py`, `Dockerfile`, `pyproject.toml`, `alembic/`, and the test suite. Every item below is tied to a specific file, not a general guess.

Bar used: **someone finds this on GitHub and runs it against their real network/subnets.** Not "does it work on my laptop."

---

## Blocking — would burn someone in real use

**1. No upper bound on scan size**
`netscan/scanner/cidr.py::validate_and_normalize_cidr` only checks that the string is a syntactically valid CIDR. Nothing stops a `/8` (or `0.0.0.0/0`) from being registered as a subnet. `expand_cidr_hosts` will materialize every host as a Python string in memory before scanning even starts — for a `/8` that's ~16.7M objects. There's no configured max prefix length anywhere in `config.py`.

**2. No concurrency guard on scan triggers**
`POST /subnets/{id}/scan` (`netscan/api/v1/subnets.py`, `trigger_subnet_scan`) creates a new `ScanJob` and fires `asyncio.create_task(...)` on every call — no check for an already-queued/running job on that subnet. Hit the endpoint 5 times in a row and you get 5 concurrent `nmap` subprocesses against the same target, uncoordinated.

**3. SQLite concurrency is untuned for the write pattern this app has**
`netscan/db.py` sets `check_same_thread: False` but never sets `PRAGMA journal_mode=WAL` or configures a busy timeout. The scheduler writes scan results in the background while the API can be writing at the same time (provisioning, key updates). Default SQLite journaling under concurrent writers means real risk of `database is locked` under any real load — not a hypothetical.

**4. Alembic exists but isn't actually the migration path**
`netscan/main.py`'s startup (`lifespan`) calls `SQLModel.metadata.create_all(engine)` directly — not `alembic upgrade head`. There's exactly one revision in `alembic/versions/`. `create_all()` only creates missing tables; it does nothing for an existing production DB when you change a column later. There is no tested, working path to upgrade an existing deployment's schema.

**5. Dashboard has no authentication by default**
Confirmed in `netscan/web/views.py` — every view depends only on `get_session`, none depend on `get_current_api_key`. Only `/api/v1/*` is behind `X-API-Key`. Anyone who can reach the port can view the network map and, via the UI, trigger scans/provisioning. This is fine on localhost; it's a real gap the moment this leaves a laptop, and nothing in the README flags it.

**6. Webhook SSRF surface**
`netscan/api/v1/webhooks.py`: webhook creation requires only `Role.OPERATOR` (not just admin), takes an arbitrary `AnyHttpUrl`, and `POST /webhooks/{id}/test` immediately fires a live request to it server-side — no private-IP/localhost/metadata-endpoint blocklist in `webhook_service.py`. An operator-level key (not even admin) can make the server issue requests to internal-only endpoints (cloud metadata services, internal admin panels) and get timing/status feedback back.

**7. The flagship scan capability is unreachable in the documented deployment path**
`Dockerfile` creates a non-root `netscan` user and runs the app as that user. ARP/SYN stealth scanning (`_detect_raw_socket_privileges` in `runner.py`) needs root or `CAP_NET_RAW`. Follow the README's own `docker run` / `docker-compose` instructions exactly as written, and you silently get unprivileged TCP-connect scanning only — the "Multi-Probe Engine" feature the README leads with. Nothing in the Docker section mentions `--cap-add=NET_RAW --cap-add=NET_ADMIN`.

---

## Should fix before the "production-grade" label is honest

**8. Webhook retries have no backoff**
`webhook_service.py`'s retry loop (`for attempt in range(WEBHOOK_MAX_RETRIES)`) has no `sleep` between attempts — three retries fire back-to-back in milliseconds. That's not meaningfully different from one attempt if the failure is transient-but-not-instant.

**9. No dependency lockfile**
`pyproject.toml` uses open-ended `>=` bounds on every dependency (FastAPI, SQLModel, httpx, etc.) with no lockfile (`uv.lock`, `poetry.lock`, or pinned `requirements.txt`) in the repo. What CI tests today and what `pip install -e .` resolves to in three months aren't guaranteed to match.

**10. The riskiest code path is the least tested**
`tests/test_scanner.py` only tests `parse_nmap_xml()` (fed hand-written XML) and `build_nmap_args()` — never `scan_cidr()`, the method that actually spawns and manages the `nmap` subprocess (timeout, kill-on-timeout, decode errors). That's the part of the codebase touching an external process and untrusted network conditions, and it's the part with zero test coverage.

**11. Rate limiter keys on raw remote IP**
`netscan/limiter.py` uses `get_remote_address` with no trusted-proxy configuration. Deploy this behind any reverse proxy or load balancer (the normal way to put a service on the internet) without extra work, and every request appears to come from the proxy's IP — the rate limit becomes one shared bucket for all users instead of per-client.

**12. Minor TOCTOU on the bootstrap-key endpoint**
`auth_keys.py::bootstrap_first_key` checks "does any key exist" and creates one non-atomically. Two near-simultaneous bootstrap calls could both pass the check and both mint an admin key. Low real-world odds (it's normally a one-time human action), but it's a real race, not a hypothetical one.

---

## Minor / polish

**13. No multi-stage Docker build** — `pip install -e .[test]` installs pytest and test deps into the runtime image; there's no separate build stage to keep the final image lean.

**14. Base image isn't pinned to a digest** — `FROM python:3.12-slim` will drift as that tag gets rebuilt upstream; no `@sha256:...` pin for reproducible builds.

---

## Bottom line

The core scanning logic (classifier state machine, safe subprocess invocation) is genuinely well-built — that part holds up. But "production-grade" as a claim doesn't survive contact with items 1–7: a stranger cloning this today can DoS their own SQLite database, get silently downgraded scan fidelity in the documented Docker path, and expose an unauthenticated dashboard and an SSRF-capable webhook feature without any warning in the docs. That's a solid personal/homelab tool with production *aspirations*, not a project ready for someone else's production network yet.
