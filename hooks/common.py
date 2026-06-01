"""Shared helpers for Claude Code worker hooks.

Hooks run inside the worker's (firejailed) Claude Code session and emit
telemetry over HTTP to /api/ingest — the only writer (prompt §1/§7). They use
only the stdlib so they run in a minimal sandbox, and they NEVER raise into the
worker: a failed emit is logged to stderr and swallowed.

Identity (which task/subtask this worker serves) and the ingest endpoint/token
are passed in via environment when the executor spawns the worker.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any


def _post(payload: dict[str, Any]) -> None:
    base = os.environ.get("DIE_FIRMA_DASHBOARD_URL", "http://127.0.0.1:4321").rstrip("/")
    token = os.environ.get("DIE_FIRMA_INGEST_TOKEN", "")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — fixed loopback URL from config
        f"{base}/api/ingest",
        data=data,
        headers={"content-type": "application/json", "x-die-firma-token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        resp.read()


def emit(kind: str, **fields: Any) -> None:
    """Best-effort telemetry emit; never breaks the worker."""
    payload: dict[str, Any] = {"kind": kind, "agent": "worker"}
    task_id = os.environ.get("DIE_FIRMA_TASK_ID")
    subtask_id = os.environ.get("DIE_FIRMA_SUBTASK_ID")
    if task_id:
        payload["task_id"] = task_id
    if subtask_id:
        payload["subtask_id"] = subtask_id
    payload.update({k: v for k, v in fields.items() if v is not None})
    try:
        _post(payload)
    except Exception as exc:  # noqa: BLE001 — hooks must never fail the worker
        print(f"[die-firma hook] ingest failed: {exc}", file=sys.stderr)


def read_hook_input() -> dict[str, Any]:
    """Parse the JSON event Claude Code passes on stdin (empty dict on error)."""
    try:
        data = json.load(sys.stdin)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}
