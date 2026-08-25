# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-25

### Added

- Multi-probe discovery engine (L2 ARP, L3 ICMP, L4 TCP SYN stealth, TCP-connect fallback) with automatic capability detection
- Safe availability model: unresponsive hosts enter `UNCERTAIN_FIREWALLED` and require both consecutive-miss threshold and quarantine duration before release
- Subnet management with CIDR validation (max /24 per scan), IP matrix view, and per-subnet scan scheduling via in-process APScheduler
- IP provisioning API (`/ips/available`) for Terraform/automation integration
- Per-IP audit history with full state-transition timeline
- HTMX dashboard (server-rendered, no Node build step): CIDR matrix grid, IP inspector drawer, scan job monitor, settings, provision helper
- Dashboard authentication: API-key sessions plus optional LDAP/AD login with hardcoded group→role mapping (`netscan-admins`→admin, `netscan-operators`→operator)
- Session-cookie-authenticated proxy routes (`/web/*`) for all dashboard writes
- REST API with API-key auth (`X-API-Key`), three roles (admin/operator/read_only), and race-safe bootstrap endpoint
- Outbound webhooks: HMAC-SHA256 signed payloads, event subscription, exponential-backoff retries
- CLI: `netscan serve` (dashboard/API modes) and `netscan login` (LDAP → API key)
- Observability: structured logging (text/JSON), access-log middleware, monotonic scan durations
- Security hardening: SECRET_KEY enforcement, CORS allow-list, global rate limiting, webhook SSRF blocklist, trusted-proxy support
- Deployment: multi-stage Dockerfile (non-root, healthcheck), Alembic migrations on startup, SQLite WAL mode
- CI: GitHub Actions (pytest matrix 3.10/3.12, ruff lint+format, docker build + healthcheck) and GHCR image publishing on version tags

[Unreleased]: https://github.com/Salar-prog/netscan/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Salar-prog/netscan/releases/tag/v0.1.0
