#!/usr/bin/env python3
"""PostToolUse hook → tool_call_end telemetry."""

from __future__ import annotations

from common import emit, read_hook_input


def main() -> int:
    data = read_hook_input()
    tool = data.get("tool_name") or data.get("tool") or "tool"
    response = data.get("tool_response")
    ok = True
    if isinstance(response, dict) and "error" in response:
        ok = False
    emit("tool_call_end", message=f"{tool}{'' if ok else ' (error)'}"[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
