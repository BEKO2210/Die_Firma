#!/usr/bin/env python3
"""Seed a deterministic example job into inbox/ (prompt §5: reproducible seeds).

Usage: python3 scripts/seed.py [--id UUID] [--inbox DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ID = "0d4f1c2e-1111-4aaa-9bbb-000000000001"

TEMPLATE = """---
id: {id}
type: code_gen
priority: 2
deadline: 2026-12-31T18:00:00+00:00
deliverable_format: file
requires_approval: false
verify: "ls *.txt"
---
# Example: generate a greeting module

Produce a small text deliverable. This is the deterministic seed used by the
mock end-to-end test — no API key required.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed an example job")
    parser.add_argument("--id", default=DEFAULT_ID)
    parser.add_argument("--inbox", default="inbox")
    args = parser.parse_args()

    inbox = Path(args.inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{args.id}.md"
    dest.write_text(TEMPLATE.format(id=args.id), encoding="utf-8")
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
