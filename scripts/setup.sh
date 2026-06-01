#!/usr/bin/env bash
# One-shot local setup: install dashboard + orchestrator dependencies.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Dashboard (npm ci)"
( cd "$ROOT/apps/dashboard" && npm ci )

echo "==> Orchestrator (pip install -e .[dev])"
( cd "$ROOT/services/orchestrator" && python3 -m pip install -e ".[dev]" )

if [ ! -f "$ROOT/.env" ]; then
  echo "==> Creating .env from template (FILL IN REAL VALUES — placeholders abort startup)"
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

echo "Setup complete. Next: ./scripts/e2e.sh for the keyless mock end-to-end."
