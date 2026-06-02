#!/usr/bin/env bash
# Reproducible mock end-to-end (claude.md §5 / prompt §5):
#   reset DB -> build + start dashboard -> seed job -> orchestrator run --once
#   -> assert outbox/<id>/ + task status "done" via the read API.
# No API key required: the mock executor drives the whole flow.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${DASHBOARD_PORT:-4322}"
export HOST="127.0.0.1"
export PORT
export DASHBOARD_HOST="127.0.0.1"
export DASHBOARD_PORT="$PORT"
export DIE_FIRMA_DASHBOARD_URL="http://127.0.0.1:${PORT}"
export DIE_FIRMA_DB_PATH="$ROOT/state/dashboard.e2e.db"
# Deterministic + keyless: force the mock executor (config.toml defaults to ollama).
export DIE_FIRMA_EXECUTOR_MODE=mock
# A real (non-placeholder) high-entropy token for the loopback-only ingest.
export DIE_FIRMA_INGEST_TOKEN="${DIE_FIRMA_INGEST_TOKEN:-e2e_$(head -c 18 /dev/urandom | od -An -tx1 | tr -d ' \n')}"

JOB_ID="0d4f1c2e-1111-4aaa-9bbb-000000000001"

cleanup() {
  [ -n "${SRV_PID:-}" ] && kill "$SRV_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> reset"
DIE_FIRMA_DB_PATH="$DIE_FIRMA_DB_PATH" ./scripts/reset.sh

echo "==> build dashboard"
( cd apps/dashboard && npm run build >/tmp/e2e_build.log 2>&1 ) || { cat /tmp/e2e_build.log; exit 1; }

echo "==> start dashboard on $DIE_FIRMA_DASHBOARD_URL"
( cd apps/dashboard && node ./dist/server/entry.mjs >/tmp/e2e_dash.log 2>&1 ) &
SRV_PID=$!

# Wait for readiness (metrics endpoint returns 200).
for _ in $(seq 1 30); do
  if curl -sf "$DIE_FIRMA_DASHBOARD_URL/api/metrics" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
curl -sf "$DIE_FIRMA_DASHBOARD_URL/api/metrics" >/dev/null || { echo "dashboard did not start"; cat /tmp/e2e_dash.log; exit 1; }

echo "==> seed job"
python3 scripts/seed.py --id "$JOB_ID" >/dev/null

echo "==> orchestrator run --once (mock executor)"
( cd services/orchestrator && python3 -m die_firma.cli run --once )

echo "==> assert deliverable in outbox"
test -f "outbox/$JOB_ID/SUMMARY.md" || { echo "FAIL: no outbox SUMMARY.md"; exit 1; }

echo "==> assert task status == done"
STATUS="$(curl -sf "$DIE_FIRMA_DASHBOARD_URL/api/tasks" \
  | python3 -c "import sys,json;ts=json.load(sys.stdin)['tasks'];print(next((t['status'] for t in ts if t['id']=='$JOB_ID'),'MISSING'))")"
echo "    status=$STATUS"
[ "$STATUS" = "done" ] || { echo "FAIL: expected done, got $STATUS"; cat /tmp/e2e_dash.log; exit 1; }

echo "E2E OK: job $JOB_ID -> outbox + status done"
