# Contributing to NetScan

Thanks for your interest in contributing. Here's how to get started.

## Development Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/Salar-prog/netscan.git
   cd netscan
   ```

2. Install in editable mode with test dependencies:
   ```bash
   pip install -e ".[test]"
   ```

3. Install nmap (required for the scanner):
   ```bash
   sudo apt install nmap   # Debian/Ubuntu
   brew install nmap       # macOS
   ```

4. Copy the example env file and adjust as needed:
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
  scanner/         # Nmap runner, CIDR utils, classifier
  services/        # Scan scheduler, webhook dispatcher
  web/             # HTMX dashboard, Jinja2 templates
  config.py        # Settings via pydantic-settings
  models.py        # SQLModel schemas
  main.py          # FastAPI app, lifespan, middleware
tests/             # Test suite
alembic/           # Database migrations
```

## Submitting Changes

1. Create a branch from `main`:
   ```bash
   git checkout -b your-feature
   ```

2. Make your changes. Keep commits focused -- one logical change per commit.

3. Run the full test suite before pushing:
   ```bash
   pytest -v
   ```

4. Push and open a pull request against `main`.

## Code Style

- Follow existing patterns in the codebase.
- Use type hints on function signatures.
- Keep functions small and focused.
- No new dependencies without discussion (open an issue first).

## Reporting Issues

Open a GitHub issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS
