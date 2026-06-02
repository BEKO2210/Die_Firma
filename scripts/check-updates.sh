#!/usr/bin/env bash
# Dependency update checker (review §10). Reports newer stable versions for the
# Python and Node dependencies so DEPENDENCIES.md / config can be refreshed
# deliberately. Read-only: it never edits files or installs anything.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Python (orchestrator) =="
if command -v pip >/dev/null 2>&1; then
  ( cd services/orchestrator && pip list --outdated --format=columns 2>/dev/null ) || true
else
  echo "  pip not found — skipping"
fi

echo
echo "== Node (dashboard) =="
if command -v npm >/dev/null 2>&1; then
  ( cd apps/dashboard && npm outdated || true )
else
  echo "  npm not found — skipping"
fi

echo
echo "Tip: review changes, then bump pins in DEPENDENCIES.md + the manifests and"
echo "run the full CI gates before committing. This script only reports."
