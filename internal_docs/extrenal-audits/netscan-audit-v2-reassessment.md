# NetScan — Reassessment After Fix Round

Pulled `9a7e12d..8d96c64` (59 files, +3216/-474) and read the actual diffs — not the commit messages. Going through the original 14 by number, then two new issues this round introduced.

**Scorecard: 9 fully fixed, 1 fixed-with-caveat, 1 partially fixed, 1 fixed-with-a-gap, 2 not actually fixed, 2 new issues found.**

---

## Original findings, rechecked

**1. Max CIDR prefix length — ✅ Fixed.** `MAX_SCAN_PREFIX_LENGTH = 24` enforced in `validate_and_normalize_cidr`. A `/8` now gets rejected before it reaches the scanner.

**2. Concurrent scans on one subnet — ✅ Fixed.** `trigger_subnet_scan` now checks for an existing `QUEUED`/`RUNNING` job on that subnet and returns `409` instead of stacking another one.

**3. SQLite concurrency — ⚠️ Partially fixed.** `journal_mode=WAL` is set correctly and persists in the DB file — that half works. But `busy_timeout=5000` is only executed once, on a throwaway connection inside `init_db()` at startup. SQLite's `busy_timeout` is a **per-connection** setting, not a database-file property — it doesn't persist the way WAL mode does. Every real request opens a fresh connection through `get_session()`, and none of those ever get the pragma applied, so they're running with SQLite's default timeout of 0. Under real write contention you'll still get an immediate `database is locked` instead of the 5-second wait this was supposed to buy you. Fix needs a `@event.listens_for(engine, "connect")` hook that sets the pragma on every new connection, not a one-time call.

**4. Alembic wired to startup — ✅ Fixed.** `lifespan()` now calls `alembic_command.upgrade(alembic_cfg, "head")` before the app serves traffic. Confirmed in `main.py`.

**5. Dashboard authentication — ⚠️ Fixed, with a gap.** `_require_dashboard_user` + `_require_role` now gate every view and write route — real change, not cosmetic. For API-key-derived sessions, `is_active` is re-checked against the DB on every single request, so revoking a key kills the session immediately. Good.

The gap: LDAP-derived sessions bake `role` into the signed cookie at login time (`create_ldap_session_cookie`) and never check back against LDAP afterward. Pull someone's `netscan-admins` group membership, and their dashboard session keeps admin access for up to 7 days (cookie lifetime) or until they happen to log out. The two auth paths behave inconsistently — one revokes live, one doesn't.

**6. Webhook SSRF — ❌ Not fixed. Reopened through a different door.** `_is_url_blocked()` exists and is correctly called in `netscan/api/v1/webhooks.py`'s `create_webhook` — the JSON API is genuinely protected now. But this same round added `POST /web/webhooks` in `views.py` (the dashboard proxy route, built to fix the broken HTMX writes) — and it's a completely separate implementation that constructs the `Webhook` row directly, with no call to `_is_url_blocked()` anywhere in that function or in `webhook_service.py`'s dispatcher. Any OPERATOR-role dashboard session can still register a webhook pointed at `169.254.169.254` or any RFC1918 address through the UI, then fire it immediately via `/web/webhooks/{id}/test`. Same vulnerability, same severity, just moved from the API to the dashboard. The fix needs to live in one shared place both callers go through — the model layer or the dispatcher — not be re-added per-endpoint.

**7. Docker capabilities for real ARP/SYN scanning — ✅ Fixed** (via documentation, not `setcap`). README's `docker run` and compose examples now include `--cap-add=NET_RAW --cap-add=NET_ADMIN` / `cap_add: [NET_RAW, NET_ADMIN]`. Follow the docs as written now and you get real stealth scanning, not a silent downgrade. Baking the capability onto the `nmap` binary at build time (`setcap cap_net_raw,cap_net_admin+eip`) would make this work with zero extra flags and survive someone skimming past that part of the README, but what's shipped is an honest, working fix, not a nitpick I'd block on.

**8. Webhook retry backoff — ✅ Fixed.** `await asyncio.sleep(min(2**attempt, 30))` between attempts, correctly skipped after the last one. Real exponential backoff.

**9. Dependency lockfile — ✅ Fixed.** `requirements-lock.txt` added as a full pip freeze.

**10. Untested scan subprocess path — ✅ Fixed.** New tests in `test_scanner.py` (`test_scan_cidr_success`, `test_scan_cidr_timeout_kills_process`, `test_scan_cidr_nonzero_exit_raises`, `test_scan_cidr_invalid_xml_output`) now exercise `scan_cidr()` itself — timeout/kill behavior, non-zero exit codes, malformed XML — mocked at the subprocess boundary, which is the correct place to mock it. This is genuine coverage of the previously-untested part.

**11. Rate limiter behind a proxy — ✅ Fixed.** `get_client_ip()` only trusts `X-Forwarded-For` when the direct connection comes from an address in `TRUSTED_PROXIES`; defaults to the raw connection IP when unset. Secure default, correct trust model.

**12. Bootstrap-key race — ❌ Not actually fixed.** A `try/except IntegrityError` was wrapped around the commit, but nothing forces the collision it's supposed to catch. `key_hash` is `unique=True`, but it's a random 32-byte token — two concurrent bootstrap calls generate two different random hashes, so both inserts succeed independently. No new migration was added (still just the one original revision), no singleton/lock row, no unique constraint on "only one bootstrap key allowed." The check-then-insert window is exactly what it was before; the error handling added just doesn't get triggered by that race. Two people hitting bootstrap within the same window still both end up with valid admin keys.

**13. Multi-stage Docker build — ✅ Fixed.** Real `builder`/`runtime` split — `gcc`, `-dev` headers, and test dependencies stay in the builder stage; runtime only gets the compiled wheels and shared libs it needs.

**14. Pinned base image — ✅ Fixed.** `python:3.12.8-slim`, a specific version rather than a floating tag. (Digest-pinning would be the maximally paranoid version of this; a version tag is a normal, defensible bar and clears what I flagged.)

---

## New, this round

**A. LDAP filter injection.** `ldap_authenticate()` builds the search filter with `settings.LDAP_USER_SEARCH_FILTER.format(username=username)` — the raw username from the login form, unescaped, straight into an LDAP query. Default filter is `(sAMAccountName={username})`. There's no call to `ldap.filter.escape_filter_chars()` anywhere in the codebase — grepped for it, zero hits. Standard LDAP-injection surface (CWE-90): a crafted username can alter the filter's logic. The bind-as-user step afterward limits how far this goes toward full auth bypass, but filter manipulation, enumeration, and unintended-match risk are all live.

**B. LDAP defaults to plaintext.** `LDAP_START_TLS: bool = False`. Unless an operator explicitly flips this, the service-account bind password and every user's password travel unencrypted to the directory server. Not unique to this project, but worth a default-secure-config fix (or at minimum a loud warning in the docs) given everything else here defaults safe.

**C. Same root cause as #5** — the LDAP session's role isn't re-validated after login, so it's really the same "trusted-until-cookie-expires" issue applying to a second, newly-added auth path.

---

## Where this actually leaves it

Real progress: 9 of the original 14 are cleanly, correctly fixed, and two more (#7, #14) are fixed in a way I'd accept even if not the most paranoid possible version. That's not nothing — this was a fast turnaround on a long list.

But the bar you set was "someone else drops this into their production network." Item 6 is the one that matters most: the SSRF hole this whole exercise was partly about closing is **open again**, just moved to the surface you built to fix problem #5. That's the classic shape of retrofitting auth onto an app that wasn't built with it — new endpoints created to route around the old assumptions inherit none of the validation the original ones had. And #12 means the exact scenario it was supposed to prevent — two admin keys from one bootstrap window — still happens.

If I had to pick the two things to fix before touching the "production-grade" label again: **route both webhook-creation paths through the same validation function**, and **make the WAL/busy_timeout and bootstrap fixes actually reach the connections that need them** (a connect-event hook for the pragma, a real uniqueness constraint or lock for bootstrap). The LDAP module is new work, not a promised fix, but I'd treat the injection as blocking too if LDAP auth ships as a real feature rather than a preview.
