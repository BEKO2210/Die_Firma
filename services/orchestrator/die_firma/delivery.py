"""Delivery: write results to outbox/<id>/ and, for code tasks, commit them on
a fresh branch feature/task-<id> inside an isolated work copy (prompt §1).

Never operates in-place on an original repo: it works only in work/<id>/.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeliveryResult:
    outbox_dir: Path
    branch: str | None


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed git args, no shell
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def deliver(
    *,
    job_id: str,
    deliverable_format: str,
    workdir: Path,
    outbox_root: Path,
    summary: str,
) -> DeliveryResult:
    out = outbox_root / job_id
    out.mkdir(parents=True, exist_ok=True)

    # Copy every artifact produced in the workdir into the outbox.
    if workdir.is_dir():
        for item in sorted(workdir.iterdir()):
            if item.is_file():
                shutil.copy2(item, out / item.name)
    (out / "SUMMARY.md").write_text(summary, encoding="utf-8")

    branch: str | None = None
    if deliverable_format == "git_branch":
        branch = f"feature/task-{job_id}"
        if not (workdir / ".git").exists():
            _git(["init", "-q"], workdir)
            _git(["config", "user.email", "die-firma@localhost"], workdir)
            _git(["config", "user.name", "Die Firma"], workdir)
            # Automated deliverable commits must never depend on a signing key.
            _git(["config", "commit.gpgsign", "false"], workdir)
        _git(["checkout", "-q", "-B", branch], workdir)
        _git(["add", "-A"], workdir)
        _git(
            [
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                f"task {job_id}: automated deliverable",
            ],
            workdir,
        )

    return DeliveryResult(outbox_dir=out, branch=branch)
