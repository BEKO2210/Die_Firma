#!/usr/bin/env python3
"""Stop hook → marks the end of the worker's main turn."""

from __future__ import annotations

from common import emit, read_hook_input


def main() -> int:
    read_hook_input()
    emit("log", message="worker session stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
