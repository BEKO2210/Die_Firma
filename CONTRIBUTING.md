# Contributing to Die Firma

Thanks for your interest! This guide gets you from clone to a green PR.

## Project layout

- `apps/dashboard` — Astro/TypeScript read-model dashboard (owns the SQLite DB
  + `/api/ingest` + SSE). The **only** DB writer.
- `services/orchestrator` — Python orchestrator (dispatcher / worker / reviewer
  / sentinel), CLI, plugins.
- `tasks/` — custom task plugins (see `tasks/README.md`).
- `hooks/`, `scripts/`, `.github/workflows/`, `systemd/` — glue, CI, ops.

The architecture is a deterministic one-way dataflow: Python never writes the
DB, it only POSTs telemetry to the dashboard. Keep that invariant.

## Developer setup

Prerequisites: **Node ≥ 22**, **Python ≥ 3.11**.

```bash
# Dashboard
cd apps/dashboard && npm ci

# Orchestrator (use a virtualenv)
cd services/orchestrator && python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

## Run the gates locally (must be green before a PR)

```bash
# Dashboard
cd apps/dashboard
npm run typecheck && npm run test:coverage && npm run build

# Orchestrator
cd services/orchestrator
ruff check . && ruff format --check . && mypy die_firma && pytest

# Full mock end-to-end (no API key)
./scripts/e2e.sh
```

These mirror CI (`.github/workflows/ci.yml`): lint, format, strict type-check,
unit tests with coverage gates, build, and the mock E2E. PRs cannot merge red.

## Coding standards

- **Python:** `ruff` (lint + format, line length 100), `mypy --strict`. Public
  functions/classes carry docstrings; prefer pure, testable functions.
- **TypeScript:** `strict` + `noUncheckedIndexedAccess`. Logic-critical `lib/`
  modules are held at high/100% coverage (see `vitest.config.ts`).
- Keep new code in the style of its neighbours; match comment density and naming.
- Adding a new **task type** touches two contracts: `die_firma/models.py`
  *and* `apps/dashboard/src/lib/types.ts`. The canonical list lives in
  [`contracts/task-types.json`](contracts/task-types.json) — update it first,
  mirror the change in both modules, and the drift-guard tests
  (`test_contracts.py` / `contracts.test.ts`) enforce they stay in sync. Adding
  behaviour to an existing type needs only a plugin under `tasks/`.

## Tests

- Every behavioural change ships with tests. Pure logic → unit tests; new
  endpoints → request/projection tests.
- Optional: mutation testing (`scripts/mutation.sh`) and the seeded chaos tests
  (`tests/test_chaos.py`).

## Commits & PRs

- Branch off `main`; use clear, imperative commit subjects (Conventional
  Commits style: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- Update `CHANGELOG.md` (Unreleased section) and relevant docs.
- Open the PR against `main`; fill in the template. Keep PRs focused.

## Security

Never commit secrets. Report vulnerabilities privately (see
[`SECURITY.md`](SECURITY.md)) rather than in a public issue.

By contributing you agree your contributions are licensed under the project's
[MIT License](LICENSE).
