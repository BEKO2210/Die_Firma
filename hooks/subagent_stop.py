#!/usr/bin/env python3
"""SubagentStop hook → records a sub-agent finishing."""

from __future__ import annotations

from common import emit, read_hook_input


def main() -> int:
    read_hook_input()
    emit("log", message="worker subagent stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
