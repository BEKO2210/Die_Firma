<!-- Thanks for contributing! Keep PRs focused. See CONTRIBUTING.md. -->

## What & why

<!-- Summary of the change and the problem it solves. Link issues: Closes #123 -->

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor / tech debt
- [ ] Docs / CI

## Checklist

- [ ] Gates pass locally: `ruff check`, `ruff format --check`, `mypy die_firma`,
      `pytest` (orchestrator) and `npm run typecheck`, `npm run test:coverage`,
      `npm run build` (dashboard).
- [ ] Mock E2E passes: `./scripts/e2e.sh`.
- [ ] Tests added/updated for the change.
- [ ] `CHANGELOG.md` (Unreleased) and docs updated if user-facing.
- [ ] No secrets committed; one-way dataflow invariant preserved (Python never
      writes the DB).
