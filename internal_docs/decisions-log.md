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

---

## 2026-08-25: CSRF protection re-evaluation

**Q: After adding session cookies, should we add CSRF tokens?**
A: No. HTMX writes will go through server-side `/web/*` proxy routes (not client-side API calls). Same-origin POST from the browser — CSRF not applicable for an internal tool with no cross-site form targets.

---

## 2026-08-25: Dashboard authentication approach

**Q: How should dashboard users authenticate?**
A: Dual mode. LDAP/AD when `LDAP_ENABLED=true` (username/password → session cookie). API key otherwise (existing behavior). Session cookie format: `ak:{key_hash}:{timestamp}:{sig}` for API keys, `ldap:{username}:{role}:{timestamp}:{sig}` for LDAP.

---

## 2026-08-25: LDAP group mapping

**Q: How to map LDAP groups to NetScan roles?**
A: Hardcoded mapping in `netscan/auth/ldap.py`:
- `netscan-admins` → ADMIN
- `netscan-operators` → OPERATOR
- All others → READ_ONLY

Not configurable via env vars. YAGNI — can add `LDAP_GROUP_MAP` later if needed.

---

## 2026-08-25: LDAP failure behavior

**Q: What happens when LDAP server is down?**
A: Reject the login. Scripts use API keys (unaffected). Operators use LDAP → if LDAP is down, they wait. No fallback to "allow anyone" — that defeats the purpose.

---

## 2026-08-25: Dashboard write operations

**Q: Dashboard HTMX forms POST to `/api/v1/*` which require `X-API-Key` header. How to fix?**
A: Server-side proxy routes under `/web/*`. The dashboard already has session cookies. Proxy routes check cookie auth + role permission, then call the same service functions the API routes use. No duplication of business logic — just an auth adapter layer.

---

## 2026-08-25: Session cookie role handling

**Q: How does the session cookie carry the role?**
A: The cookie embeds the role at sign time. `ldap:{username}:{role}:{timestamp}:{sig}`. Role comes from LDAP group mapping. For API key sessions, role is looked up from DB at validation time (existing behavior). Two different flows, one validation function with a `type` field in the return dict.

---

## 2026-08-25: CLI LDAP login

**Q: Should `netscan login` support LDAP?**
A: Yes. `netscan login` prompts for username/password, binds to LDAP, on success creates an API key with the mapped role, prints the raw key. User saves it. The CLI never stores credentials — it just bootstraps an API key.

---

## 2026-08-25: python-ldap as dependency

**Q: python-ldap requires system-level libldap2-dev. Is that OK?**
A: Yes. The Dockerfile already installs build tools for compilation. For local dev, `sudo apt install libldap2-dev libsasl2-dev` is documented in README. python-ldap is the standard LDAP library for Python — no viable pure-Python alternative for AD integration.

---

## 2026-08-27: Overlapping subnet detection

**Q: Should overlapping CIDRs be rejected on subnet creation?**
A: Yes. Use `ipaddress.IPv4Network.overlaps()` to check against all existing subnets. Reject if the new CIDR overlaps with any existing one (excluding exact duplicates, which are caught by the unique constraint). Prevents ambiguous IP lookups when the same IP exists in two overlapping subnets.

---

## 2026-08-27: Soft key revoke vs hard delete

**Q: Should DELETE /auth/keys/{id} hard-delete the key or soft-revoke?**
A: Soft-revoke. Set `revoked_at` timestamp and `is_active=false`. The row stays for audit trail (which key did what). Add PATCH endpoint for renaming, reassigning role, or setting expiry. This preserves the audit trail that hard-delete destroys.

---

## 2026-08-27: Correlation IDs

**Q: Should we add correlation IDs for request tracing?**
A: Yes. Generate a UUID per request (`X-Request-ID` header). If the client sends one, echo it back. Include in access logs. Lightweight, no external deps, standard practice for distributed tracing.

---

## 2026-08-27: Graceful shutdown

**Q: Should we drain in-flight tasks on shutdown?**
A: Yes. Track webhook tasks in a set with done-callbacks. On lifespan exit, `await asyncio.gather()` on all tracked tasks with `return_exceptions=True`. Bounded by asyncio default timeout. Prevents orphaned webhook deliveries on deploy.
