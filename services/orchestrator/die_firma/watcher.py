"""Inbox watcher: parse inbox/*.md (YAML frontmatter + body) into Jobs.

The filesystem is the single source of truth (prompt §1). Already-processed
jobs are tracked by id in the state dir so a poll is idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import Job

FRONTMATTER_FENCE = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown document into (frontmatter mapping, body)."""
    stripped = text.lstrip("﻿")  # tolerate BOM
    if not stripped.startswith(FRONTMATTER_FENCE):
        raise ValueError("missing YAML frontmatter fence (---)")
    parts = stripped.split(FRONTMATTER_FENCE, 2)
    # parts == ['', '<yaml>', '<body>']
    if len(parts) < 3:
        raise ValueError("unterminated YAML frontmatter")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")
    return meta, parts[2].strip()


def parse_job(text: str, source_path: Path | None = None) -> Job:
    meta, body = parse_frontmatter(text)
    return Job(**meta, body=body, source_path=source_path)


def load_job_file(path: Path) -> Job:
    return parse_job(path.read_text(encoding="utf-8"), source_path=path)


def scan_inbox(inbox_dir: Path) -> list[Path]:
    """Markdown files in the inbox, sorted for deterministic ordering."""
    if not inbox_dir.is_dir():
        return []
    return sorted(p for p in inbox_dir.glob("*.md") if p.is_file())


class ProcessedRegistry:
    """Tracks processed job ids in state/processed.json (idempotent polling)."""

    def __init__(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        self._path = state_dir / "processed.json"
        self._ids: set[str] = set()
        if self._path.is_file():
            try:
                self._ids = set(json.loads(self._path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError):
                self._ids = set()

    def seen(self, job_id: str) -> bool:
        return job_id in self._ids

    def mark(self, job_id: str) -> None:
        self._ids.add(job_id)
        self._path.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")


class ApprovalRegistry:
    """Tracks operator approvals (state/approved.json) for gated jobs."""

    def __init__(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        self._path = state_dir / "approved.json"
        self._ids: set[str] = set()
        if self._path.is_file():
            try:
                self._ids = set(json.loads(self._path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError):
                self._ids = set()

    def approved(self, job_id: str) -> bool:
        return job_id in self._ids

    def approve(self, job_id: str) -> None:
        self._ids.add(job_id)
        self._path.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")
