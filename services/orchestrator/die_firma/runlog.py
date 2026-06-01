"""Append-only audit log per job (runlog/<task_id>.log) — prompt §1.

Deterministic, plain-text, one line per event. Useful for debugging and as a
future fine-tuning dataset.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


class RunLog:
    def __init__(self, runlog_dir: Path, task_id: str) -> None:
        runlog_dir.mkdir(parents=True, exist_ok=True)
        self._path = runlog_dir / f"{task_id}.log"

    @property
    def path(self) -> Path:
        return self._path

    def append(self, message: str) -> None:
        ts = datetime.now(UTC).isoformat()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts}\t{message}\n")
