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

# Missing pyproject.toml

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
