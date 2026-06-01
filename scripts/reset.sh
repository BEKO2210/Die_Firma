#!/usr/bin/env bash
# Reset the read-model DB + orchestrator state for a clean, reproducible run
# (claude.md §5). Does NOT touch source or committed config.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DB_PATH="${DIE_FIRMA_DB_PATH:-$ROOT/state/dashboard.db}"
rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"

rm -f state/processed.json state/approved.json

for d in work outbox runlog; do
  find "$d" -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} + 2>/dev/null || true
done

echo "reset: removed $DB_PATH and orchestrator state (work/outbox/runlog cleared)"
