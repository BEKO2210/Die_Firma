#!/usr/bin/env bash
# Mutation testing helper (review §7). Non-blocking, run on demand — NOT part of
# the default CI gate. Verifies the test suites kill injected logic mutants.
#
#   scripts/mutation.sh python     # mutmut over the orchestrator core
#   scripts/mutation.sh dashboard  # Stryker over the dashboard lib
#   scripts/mutation.sh            # both
set -euo pipefail
cd "$(dirname "$0")/.."

run_python() {
  echo "==> mutmut (orchestrator)"
  cd services/orchestrator
  pip install -e ".[dev,mutation]" >/dev/null
  mutmut run || true
  mutmut results || true
  cd - >/dev/null
}

run_dashboard() {
  echo "==> Stryker (dashboard)"
  cd apps/dashboard
  npm ci >/dev/null
  npx --yes @stryker-mutator/core@latest run || true
  cd - >/dev/null
}

case "${1:-all}" in
  python)    run_python ;;
  dashboard) run_dashboard ;;
  all)       run_python; run_dashboard ;;
  *) echo "usage: $0 [python|dashboard|all]" >&2; exit 2 ;;
esac
