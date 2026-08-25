# NetScan System Walkthrough

## Summary of Completed Work

We built and verified the **NetScan Production-Grade IP Discovery and Availability Platform** inside your repository.

---

## 1. Components Built

### 📡 Discovery Engine & Safe Heuristics (`netscan/scanner/`)
* **`cidr.py`**: Accurate IPv4 CIDR validation, usable host expansion, network metadata extraction.
* **`runner.py`**: Multi-probe asynchronous Nmap executor with capability detection (`CAP_NET_RAW`/root detection for ARP & TCP SYN stealth sweeps, with automatic fallback to unprivileged TCP Connect sweeps).
* **`classifier.py`**: Safe availability classifier preventing premature IP reclamation:
  * Transitions hosts to `UNCERTAIN_FIREWALLED` on first unresponsiveness.
  * Only releases to `AVAILABLE_CANDIDATE` when **both** consecutive miss count (e.g. 3) and quarantine duration (e.g. 48h) are fulfilled.
  * Honors permanent `ASSIGNED_RESERVED` locks while continuing telemetry updates.

### ⚙️ Services & Background Scheduling (`netscan/services/`)
* **`scan_service.py`**: End-to-end subnet scan reconciliation, audit log creation, and statistics updates.
* **`scheduler_service.py`**: In-process `APScheduler` managing automated recurring scan intervals per subnet with zero external broker dependencies.
* **`webhook_service.py`**: Outbound HTTP POST notification dispatcher with **full IP object snapshots** and HMAC-SHA256 signatures.

### 🔌 REST API Layer (`netscan/api/v1/`)
* **`/api/v1/subnets`**: Subnet CRUD, statistics calculation, live scan triggers, and visual CIDR matrix endpoint.
* **`/api/v1/ips`**: Filtered IP searches, detailed address inspection, reservation toggles, and audit timeline.
* **`/api/v1/ips/available`**: Automated next-available IP provisioning endpoint for Terraform/automation.
* **`/api/v1/scans`**: Historical and active scan job inspection.
* **`/api/v1/webhooks`**: Outbound webhook management & test payload dispatch.
* **`/api/v1/auth/keys`**: Scoped API key creation, verification, and revocation.

### 💻 Web Dashboard (`netscan/web/`)
* Built with **FastAPI + Jinja2 + HTMX + Tailwind CSS** (zero Node.js build step):
  * **Subnet & Pool Overview (`/`)**: Metric cards, capacity progress bars, and modal for adding new CIDRs.
  * **Interactive Visual Matrix (`/subnets/{id}/matrix`)**: Responsive tile grid with live color coding (Active = Green, Uncertain = Amber, Reserved = Blue, Available = Slate).
  * **Slide-over IP Inspector (`/web/ips/{ip}/drawer`)**: MAC vendor, open ports with service versions, reservation toggle, and historical audit trail.
  * **Available IP Provisioner (`/provision`)**: Quick multi-IP query widget with copy-to-clipboard.
  * **Scan Job History (`/scans`)**: Real-time status badges and execution metrics.
  * **Settings (`/settings`)**: API keys and webhook manager.

---

## 2. Production Hardening (Phases 1-3)

### Phase 1 — Crash Bugs & Functional Breakage
- Created `pyproject.toml` with all dependencies
- Removed dead `StaticFiles` mount (404 on `/static`)
- Fixed CORS: `ALLOWED_ORIGINS` from Settings (no more hardcoded wildcard)
- Fixed drawer 404 bug (no phantom IP creation on empty drawer)
- Fixed drawer HTMX form (switched to JS fetch with JSON body)
- Fixed provision page (server-side `/web/ips/available` endpoint)
- Added `conftest.py` with shared `client` and `auth_client` fixtures
- Removed 29 `.pyc` files from tracking; expanded `.gitignore`
- Normalized all CRLF line endings to LF

### Phase 2 — Security Hardening
- Removed open-access bootstrap (API key required on all endpoints)
- Added `SECRET_KEY` validation at startup (blocks production without key)
- Added `ALLOWED_ORIGINS` from Settings (comma-separated)
- Added webhook URL validation via `AnyHttpUrl`
- Added webhook secret auto-generation (never exposed after creation via list endpoint)
- Added global rate limiting via slowapi (120/min default, `/health` exempt)
- Fixed `classifier.py` type hint (`Optional[Dict[str, Any]] = None`)
- Removed stale signing secret input from settings.html

### Phase 3 — Deploy Infrastructure
- Initialized alembic with SQLModel metadata + Settings integration
- Added initial migration creating all 6 tables
- Created `Dockerfile` (Python 3.12-slim, nmap, non-root user, healthcheck)
- Created `.dockerignore` for clean builds

### CSRF — Intentionally Skipped
No session cookies in the app; auth is header-only (`X-API-Key`). CSRF protection does not apply.

---

## 3. Test Verification

19/19 tests pass across 5 suites:

```
platform linux -- Python 3.13.5, pytest-9.1.1

tests/test_api.py::test_health_check PASSED
tests/test_api.py::test_subnet_crud_and_matrix PASSED
tests/test_api.py::test_available_ips_query PASSED
tests/test_api.py::test_webhook_crud_and_test PASSED
tests/test_api.py::test_api_key_management PASSED
tests/test_cidr.py::test_validate_and_normalize_cidr PASSED
tests/test_cidr.py::test_expand_cidr_hosts_24 PASSED
tests/test_cidr.py::test_expand_cidr_hosts_30 PASSED
tests/test_cidr.py::test_expand_cidr_hosts_32 PASSED
tests/test_cidr.py::test_subnet_metadata PASSED
tests/test_cidr.py::test_is_ip_in_cidr PASSED
tests/test_classifier.py::test_positive_probe_activates_host PASSED
tests/test_classifier.py::test_active_host_becomes_uncertain_on_first_miss PASSED
tests/test_classifier.py::test_uncertain_host_remains_uncertain_if_quarantine_not_met PASSED
tests/test_classifier.py::test_uncertain_host_becomes_available_when_quarantine_and_misses_met PASSED
tests/test_classifier.py::test_reserved_ip_retains_reserved_status PASSED
tests/test_scanner.py::test_nmap_xml_parsing PASSED
tests/test_web.py::test_dashboard_views PASSED
tests/test_web.py::test_matrix_and_drawer_views PASSED

======================== 19 passed in 1.18s ========================
```

### Runtime Verification
- Health check: 200 OK, shows database and nmap status
- Auth required on all API endpoints (401 without key)
- Bootstrap: creates first admin key, disabled after first use (403)
- CORS: returns `Access-Control-Allow-Origin` when Origin header present
- Rate limiting: global 120/min, `/health` exempt
- Webhook URL validation: rejects invalid URLs (422)
- Webhook secret: returned once on creation, hidden on list endpoint

### Container Verification
- `docker build -t netscan:test .` succeeds
- Container starts on port 8002, health check returns 200
- Bootstrap works inside container
- Web dashboard loads (HTTP 200)
- Container stops cleanly

---

## 4. Git Repository Status

All code, templates, tests, and documentation committed to the `development` branch:

```
0362188 feat: phase 3 deploy infrastructure
e62041d feat: phase 2 security hardening
9fb1c20 fix: phase 1 crash bugs and functional breakage
2769869 feat: implement complete NetScan IP discovery platform, API, scheduler, and dashboard
d8fe632 docs: update PLAN.md with refined architecture decisions
b0ae9c4 docs: add detailed PLAN.md with architecture decisions
```
