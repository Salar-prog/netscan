# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ |

## Reporting a Vulnerability

Please report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/Salar-prog/netscan/security/advisories/new)
("Report a vulnerability").

Do **not** open a public issue for security reports.

Include: affected version/commit, environment, reproduction steps, and impact
assessment. You can expect an initial response within 7 days.

## Security Model Notes

- All `/api/v1` endpoints require `X-API-Key`; the bootstrap endpoint is open only until the first key exists.
- Dashboard sessions use HMAC-signed cookies; set `SECRET_KEY` in production (startup fails otherwise).
- Webhook secrets are returned once at creation and never exposed afterwards.
- LDAP login failures always reject authentication — there is no fallback.
- Webhook URLs are validated against a private/metadata IP blocklist (SSRF protection).

See `docs/api.md` for endpoint auth requirements and
`netscan/config.py` for all hardening-related settings.
