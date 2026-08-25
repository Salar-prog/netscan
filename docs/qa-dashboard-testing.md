# Dashboard QA Test Plan

Manual testing guide for dashboard contributors. Run these before pushing dashboard changes.

## Prerequisites

```bash
pip install -e ".[test]"
netscan serve --reload
# Open http://localhost:8000 in browser
```

## Test Matrix

### Authentication (6 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 1 | Login page loads | GET `/login` | Form with API key input, no error |
| 2 | Valid API key login | Enter valid key, submit | Redirect to `/`, `netscan_session` cookie set |
| 3 | Invalid API key login | Enter garbage, submit | Error message, no cookie |
| 4 | Logout | Click logout or GET `/logout` | Cookie cleared, redirect to `/login` |
| 5 | Protected route without cookie | GET `/` without cookie | Redirect to `/login` |
| 6 | Protected route with expired cookie | Set expired cookie, GET `/` | Redirect to `/login` |

### LDAP Authentication (4 tests, requires LDAP_ENABLED=true)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 7 | LDAP login form | GET `/login` | Username/password fields shown (not API key) |
| 8 | Valid LDAP login | Enter username + password | Redirect to `/`, `ldap:` cookie set |
| 9 | Invalid LDAP credentials | Enter wrong password | Error message, no cookie |
| 10 | LDAP cookie grants access | Set valid `ldap:` cookie, GET `/` | Dashboard loads |

### Subnets (5 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 7 | Subnet list loads | GET `/` | Table with subnets, CIDR column |
| 8 | Create subnet | Fill form, submit | New row in table |
| 9 | Trigger scan | Click scan button | Job created, status updates |
| 10 | Delete subnet | Click delete, confirm | Row removed |
| 11 | View subnet details | Click CIDR link | Drawer opens with IP list |

### IP Management (5 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 12 | IP matrix loads | GET `/` | Grid of IPs with color coding |
| 13 | IP status colors | Check matrix | Green=active, yellow=uncertain, red=unreachable, gray=available |
| 14 | IP drawer opens | Click IP in matrix | Side drawer with IP details |
| 15 | Reserve IP | In drawer, set reserved | IP status changes to reserved |
| 16 | IP history | In drawer, click history | Audit trail shown |

### Settings (6 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 17 | Settings page loads | GET `/settings` | API keys table + webhooks table |
| 18 | Generate key | Click generate, enter name | New key shown once, appears in table |
| 19 | Revoke key | Click revoke | Key removed from table |
| 20 | Create webhook | Fill URL, select events | Webhook appears in table, secret shown once |
| 21 | Test webhook | Click test button | Notification sent, response shown |
| 22 | Delete webhook | Click delete | Webhook removed |

### Scan Jobs (3 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 23 | Scans page loads | GET `/scans` | Table with scan jobs |
| 24 | Job status updates | Trigger scan, wait | Status changes from QUEUED → RUNNING → COMPLETED |
| 25 | Job history | Check scans page after multiple scans | All jobs listed with timestamps |

### API Key Header Auth (4 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 26 | API list subnets | `curl -H "X-API-Key: <key>" /api/v1/subnets` | 200, JSON array |
| 27 | API create subnet | POST with JSON body + API key | 201, subnet created |
| 28 | API without key | `curl /api/v1/subnets` | 401 |
| 29 | API with wrong key | `curl -H "X-API-Key: wrong" /api/v1/subnets` | 401 |

### Responsive Layout (3 tests)

| # | Test | Steps | Expected |
|---|------|-------|----------|
| 30 | Desktop layout | 1920x1080 | Full sidebar, matrix grid |
| 31 | Tablet layout | 768x1024 | Collapsible sidebar |
| 32 | Mobile layout | 375x667 | Hamburger menu, stacked layout |

## Test Fixtures

```python
# conftest.py provides:
client          # Unauthenticated TestClient
auth_client     # TestClient + bootstrapped API key
dashboard_client # TestClient with valid session cookie
make_key_headers # Factory for API key headers
```

## Running Specific Tests

```bash
# All dashboard tests
pytest tests/test_web.py -v

# Auth tests only
pytest tests/test_web.py -v -k "login or logout or cookie"

# E2E audit tests
pytest tests/test_e2e_audit_fixes.py -v

# Full suite
pytest -v
```

## Common Failure Modes

1. **401 on HTMX writes**: Forms target `/api/v1/*` which needs `X-API-Key` header. Must use `/web/*` proxy routes.
2. **Cookie not sent**: Browser blocks cookie if `SameSite` is wrong. Check `session.py` settings.
3. **HX-Redirect not working**: HTMX needs `HX-Redirect` header, not `Location` header for redirects.
4. **Session expired**: Cookie TTL is 24h. Re-login required.
