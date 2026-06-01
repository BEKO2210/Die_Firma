"""Reviewer: validate a job's deliverable.

If the job supplies a reproducible `verify` command it is run in the work
directory and its exit code decides pass/fail (prompt §4). With no command the
review passes by default (nothing to assert against).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReviewResult:
    passed: bool
    detail: str


def review(verify_cmd: str | None, workdir: Path, timeout: float = 300.0) -> ReviewResult:
    if verify_cmd is None or verify_cmd.strip() == "":
        return ReviewResult(passed=True, detail="no verify command; passed by default")
    try:
        proc = subprocess.run(  # noqa: S602 — verify command is operator-supplied
            verify_cmd,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ReviewResult(passed=False, detail=f"verify timed out after {timeout}s")
    detail = (proc.stdout + proc.stderr).strip()[-2000:]
    return ReviewResult(passed=proc.returncode == 0, detail=detail or f"exit {proc.returncode}")
