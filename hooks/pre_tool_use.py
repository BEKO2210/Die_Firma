#!/usr/bin/env python3
"""PreToolUse hook → tool_call_start telemetry."""

from __future__ import annotations

from common import emit, read_hook_input


def main() -> int:
    data = read_hook_input()
    tool = data.get("tool_name") or data.get("tool") or "tool"
    emit("tool_call_start", message=str(tool)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
