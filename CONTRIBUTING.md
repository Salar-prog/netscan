# Contributing to NetScan

Thanks for your interest in contributing. Here's how to get started.

## Development Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/Salar-prog/netscan.git
   cd netscan
   ```

2. Install system headers required by `python-ldap`:
   ```bash
   sudo apt install libldap2-dev libsasl2-dev   # Debian/Ubuntu
   brew install openldap                        # macOS
   ```

3. Install in editable mode with test dependencies:
   ```bash
   pip install -e ".[test]"
   ```

4. Install nmap (required for the scanner):
   ```bash
   sudo apt install nmap   # Debian/Ubuntu
   brew install nmap       # macOS
   ```

5. Copy the example env file and adjust as needed:
   ```bash
   cp .env.example .env
   ```

## Running the App

```bash
uvicorn netscan.main:app --host 0.0.0.0 --port 8000 --reload
```

Dashboard: http://localhost:8000/
API docs: http://localhost:8000/docs

## Running Tests

```bash
pytest -v
```

Tests use an in-memory SQLite database -- no nmap or API keys required.

## Project Structure

```
netscan/
  api/v1/          # REST API endpoints
  api/auth.py      # API key authentication
  auth/            # LDAP/AD authentication (bind + group→role mapping)
  scanner/         # Nmap runner, CIDR utils, classifier
  services/        # Scan orchestration, scheduler, webhook dispatcher
  web/             # HTMX dashboard, templates, session cookies, /web/* proxy routes
  config.py        # Settings via pydantic-settings
  models.py        # SQLModel schemas
  main.py          # FastAPI app factory, lifespan, middleware
  cli.py           # netscan serve / netscan login
tests/             # Test suite (pytest)
alembic/           # Database migrations
docs/              # Public docs (API reference, QA guide)
internal_docs/     # Internal dev logs (plans, progress, decisions)
```

## Submitting Changes

1. Create a branch from `main`:
   ```bash
   git checkout -b your-feature
   ```

2. Make your changes. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`) — one logical change per commit.

3. Run the full test suite before pushing:
   ```bash
   pytest -v
   ```

4. Run linter and formatter:
   ```bash
   ruff check netscan/
   ruff format --check netscan/
   ```

5. Push and open a pull request against `main`. CI will run automatically (lint, test, Docker build).

## Code Style

- Follow existing patterns in the codebase.
- Use type hints on function signatures.
- Keep functions small and focused.
- Run `ruff check` and `ruff format` before committing (config in `pyproject.toml`).
- No new dependencies without discussion (open an issue first).

## Reporting Issues

Open a [GitHub issue](https://github.com/Salar-prog/netscan/issues) with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS

**Security vulnerabilities must not be reported publicly.** Use
[private security advisories](https://github.com/Salar-prog/netscan/security/advisories/new)
instead — see [SECURITY.md](SECURITY.md) for the disclosure policy.
