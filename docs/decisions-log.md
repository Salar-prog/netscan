# Decisions Log

Every clarifying question asked and the answer given. Most recent first.

---

## 2026-08-24: CI/CD tooling

**Q: Ruff vs flake8 + black + isort?**
A: Ruff. Single tool for linting and formatting, 10-100x faster than alternatives, config lives in pyproject.toml. No reason to install 3 separate tools.

**Q: How many CI jobs?**
A: Three parallel jobs: `test` (Python matrix), `lint` (ruff check + format), `docker` (build + health check). Minimal, fast, covers the failure modes that matter.

**Q: Should ruff format be enforced in CI?**
A: Yes. `ruff format --check` in CI prevents style drift. The formatter is opinionated — that's the point.

---

## 2026-08-24: SQLModel boolean queries

**Q: `Column.is_active == True` or `Column.is_active`?**
A: Direct `Column.is_active`. In SQLModel/SQLAlchemy, boolean columns are truthy by default in WHERE clauses. The `== True` pattern triggers ruff E712 and is redundant.

---

## 2026-08-24: Open-source repo setup

**Q: What license?**
A: MIT

**Q: Public or private?**
A: Public.

**Q: Should PLAN.md and walkthrough.md be kept or removed before going public?**
A: Keep them in the repo for now (team collaboration). Remove or gitignore before final public launch.

**Q: GitHub PAT exposed in conversation -- proceed or wait?**
A: Proceed, rotate after.

---

## 2026-08-24: CSRF protection

**Q: Should we add CSRF tokens to HTMX forms?**
A: Skipped. The app has no session cookies. Auth is header-only (`X-API-Key`). CSRF targets cookie-based sessions. Not applicable.

---

## 2026-08-24: Webhook secret handling

**Q: Should webhook secrets be hashed like API keys?**
A: No. The webhook dispatcher needs the raw secret to sign outbound HMAC-SHA256 payloads. Hashing would make signing impossible. Secret is stored plaintext in DB, returned once at creation, never exposed via list endpoint.

---

## 2026-08-24: Webhook URL validation

**Q: What validation on webhook URLs?**
A: `AnyHttpUrl` from Pydantic -- requires http:// or https:// scheme, valid hostname. Stored as `str()` in DB.

---

## 2026-08-24: Rate limiting approach

**Q: Per-route or global rate limiting?**
A: Global `default_limits=["120/minute"]` via slowapi. `/health` exempt. Per-route decorators removed -- slowapi requires `request` param in function signature, not worth the clutter for an internal tool.

---

## 2026-08-24: CORS configuration

**Q: How to handle CORS for production?**
A: `ALLOWED_ORIGINS` from Settings as comma-separated string. Default `*` for dev. Parsed in `main.py:45`.

---

## 2026-08-24: SECRET_KEY validation

**Q: What happens if SECRET_KEY is empty in production?**
A: `validate_for_production()` called at lifespan startup. Raises `ValueError` if `DEBUG=False` and `SECRET_KEY` is empty.

---

## 2026-08-24: Bootstrap endpoint

**Q: How does the first API key get created?**
A: `POST /api/v1/auth/keys/bootstrap` -- no auth required, auto-assigns ADMIN role, disabled after first use (returns 403 if any keys exist).

---

## 2026-08-24: Test fixtures

**Q: How to share test fixtures across test files?**
A: `conftest.py` with `client` (unauthenticated) and `auth_client` (bootstraps API key, returns `(client, headers)` tuple). Duplicate fixtures removed from `test_api.py` and `test_web.py`.

---

## 2026-08-24: Container user

**Q: Should the Docker container run as root?**
A: No. Create `netscan` user, `chown -R netscan:netscan /app` before switching. Container is non-root.
