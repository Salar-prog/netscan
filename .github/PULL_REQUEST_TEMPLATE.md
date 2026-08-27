## Summary

<!-- What does this PR do? One or two sentences. -->

## Changes

-

## Motivation & context

<!-- Why is this needed? Link issues with Fixes #N. -->

## Testing

- [ ] `pytest -v` passes locally
- [ ] `ruff check netscan/ tests/` clean
- [ ] `ruff format --check netscan/ tests/` clean
- [ ] New logic covered by tests
- [ ] Postgres tests pass (if schema changes involved)

## Checklist

- [ ] Conventional Commits style (`feat:`, `fix:`, `docs:`, `chore:`)
- [ ] No new dependencies without prior discussion
- [ ] Domain invariants respected (safe availability model, auth on `/api/v1/*`,
      webhook secret handling, dashboard writes via `/web/*` only)
