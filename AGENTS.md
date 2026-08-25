# AGENTS.md

Guidance for AI coding agents and human collaborators working on NetScan.

## Project Overview

NetScan is a production-grade IP discovery and availability tracking platform. It reconciles active network probes (L2 ARP, L3 ICMP, L4 TCP SYN) with managed subnet pools to track which IPs are active, quarantined, reserved, or available for allocation.

- **Stack:** Python 3.10+, FastAPI, SQLModel (SQLite by default), APScheduler, Jinja2 + HTMX dashboard, Alembic migrations.
- **No Node.js build step.** The dashboard is server-rendered.

## Setup & Commands

```bash
# Install with test dependencies
pip install -e ".[test]"

# Run dev server (with dashboard)
netscan serve --reload

# Run API-only server (no dashboard)
netscan serve --no-dashboard

# Or use uvicorn directly
uvicorn netscan.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest -v

# Lint and format
ruff check netscan/
ruff format --check netscan/

# Database migrations (Alembic)
alembic upgrade head
```

Notes:

- `nmap` is required at **runtime only** — the test suite uses an in-memory SQLite database and never invokes nmap.
- Configuration comes from environment variables or a `.env` file (see table in README.md).
- `SECRET_KEY` must be set when `DEBUG=false`, or startup fails with `ValueError`.

## Architecture Map

```
netscan/
  api/v1/          # REST endpoints: subnets.py, ips.py, scans.py, webhooks.py, auth_keys.py
  api/auth.py      # API key authentication dependency (X-API-Key header)
  auth/            # Enterprise auth (Phase 10):
    ldap.py        #   LDAP bind + group→role mapping
  scanner/         # Discovery engine:
    runner.py      #   async nmap wrapper, capability auto-detection, probe parsing
    classifier.py  #   state & quarantine heuristic classifier
    cidr.py        #   CIDR utilities
  services/
    scan_service.py       # scan job orchestration
    scheduler_service.py  # in-process APScheduler integration
    webhook_service.py    # outbound HMAC-SHA256 signed webhook dispatcher
  web/
    views.py       # HTMX dashboard routes (Jinja2) + /web/* proxy routes
    session.py     # HMAC-signed session cookie (ak: and ldap: formats)
    templates/     # Jinja2 templates (base, index, matrix, drawer, provision, scans, settings, login)
  config.py        # Settings via pydantic-settings (incl. LDAP config)
  models.py        # SQLModel schemas (Subnet, IPAddress, ScanJob, IPHistory, Webhook, ApiKey)
  db.py            # Engine + get_session dependency
  limiter.py       # Shared slowapi RateLimiter instance
  main.py          # FastAPI app factory, lifespan, middleware, rate limiting
  cli.py           # Click CLI: netscan serve --dashboard/--no-dashboard, netscan login
tests/             # pytest suite (conftest.py has shared fixtures)
alembic/           # DB migrations
docs/              # Internal docs (progress, changes, decisions, learnings, plans)
```

## Testing

- Fixtures live in `tests/conftest.py`:
  - `client` — TestClient with overridden in-memory SQLite session.
  - `auth_client` — same, plus a bootstrapped API key; yields `(client, {"X-API-Key": ...})`.
- Tests override the `get_session` dependency; they do not touch disk or require nmap/API keys.
- pytest asyncio mode is `auto` — async test functions work without decorators.
- Run the full suite (`pytest -v`) before pushing anything.
- CI (GitHub Actions) runs automatically on every push to `main` and every PR: lint, test (Python 3.10+3.12), Docker build.

## Code Conventions

- Type hints on all function signatures.
- Keep functions small and focused; follow patterns already in the codebase.
- LF line endings (never CRLF).
- No new dependencies without discussion first — and when adding one, declare it in `pyproject.toml` in the same commit.
- No comments unless necessary; prefer clear naming.

## Domain Invariants (do not break)

1. **Safe availability logic** (`scanner/classifier.py`): an unresponsive host becomes `UNCERTAIN_FIREWALLED`; it may only become available after meeting **both** the consecutive-miss threshold *and* the quarantine duration. Never weaken this to "ping failed = free".
2. **API-key auth**: every `/api/v1` endpoint requires authentication via `X-API-Key`. Only `/api/v1/auth/keys/bootstrap` is open, and only until the first key exists.
3. **Webhook secrets** are stored plaintext (needed to sign outbound payloads), returned once at creation, and must never be exposed via list/get endpoints.
4. **Rate limiting** via slowapi applies globally; `/health` is exempt.
5. **LDAP group mapping** is hardcoded in `netscan/auth/ldap.py`: `netscan-admins`→ADMIN, `netscan-operators`→OPERATOR, default→READ_ONLY. Do not make this configurable without explicit discussion.
6. **LDAP failure = reject login.** Never add a fallback that bypasses LDAP when the server is down. Scripts use API keys and are unaffected.
7. **Dashboard writes go through `/web/*` proxy routes**, not direct `/api/v1/*` calls. Session cookies don't carry API key headers. Proxy routes check cookie auth + role, then call service functions.

## Git Workflow

Two collaborators — use feature branches. **Never push to `main` directly.**

### Standing instructions for AI agents

For every meaningful change made inside the repo:

1. Stage and commit the change (Conventional Commits, one logical change per commit).
2. Push to a feature branch — create one from `main` first if not already on one.
3. Never commit or push directly to `main`.

### Branch & commit rules

1. Branch from `main`: `git checkout -b feat/your-feature`
2. Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:` — one logical change per commit.
3. Run `pytest -v` before pushing.
4. Open a PR against `main`; the other collaborator reviews before merge.

Branch name prefixes: `feat/`, `fix/`, `docs/`, `chore/`.

## Further Reading

- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, style, submission guide
- [README.md](README.md) — features, configuration reference, API examples
- [PLAN.md](PLAN.md) — original architecture specification
- [docs/learnings.md](docs/learnings.md) — gotchas and lessons learned (read this before debugging)
- [docs/decisions-log.md](docs/decisions-log.md) — rationale behind past decisions
- [docs/progress.md](docs/progress.md) — implementation status per phase
