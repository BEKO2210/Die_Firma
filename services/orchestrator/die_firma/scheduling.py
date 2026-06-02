"""Adaptive parallelism + job prioritisation (review §2).

The fixed two-task semaphore is safe but conservative. These pure helpers let
the orchestrator size its worker pool to the *current* machine — backing off
when the CPU is busy or VRAM is tight, and using more of the box when it is
idle — and process urgent jobs first.

Everything here is a pure function of injected readings (CPU count, load, free
VRAM), so it is fully deterministic and unit-testable; the small, side-effecting
probes that read the real machine are isolated at the bottom.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable

from .models import Job


def adaptive_worker_count(
    baseline: int,
    *,
    cpu_count: int,
    load1: float,
    min_workers: int = 1,
    ceiling: int | None = None,
    vram_free_mb: int | None = None,
    vram_per_worker_mb: int = 0,
) -> int:
    """Worker count for the current machine state.

    ``baseline`` is the configured semaphore size. ``ceiling`` is the hard upper
    bound (defaults to ``baseline``, so adaptive scaling only *reduces* unless
    the operator opts into a higher ceiling). The count tracks free CPU cores
    (``cpu_count - load1``) and, when known, is capped so the concurrent workers
    fit in free VRAM.
    """
    min_workers = max(1, min_workers)
    top = baseline if ceiling is None else max(ceiling, min_workers)
    top = max(top, min_workers)

    headroom = cpu_count - load1
    target = int(round(headroom)) if headroom >= 1 else min_workers
    target = max(min_workers, min(target, top))

    if vram_free_mb is not None and vram_per_worker_mb > 0:
        vram_cap = max(min_workers, vram_free_mb // vram_per_worker_mb)
        target = min(target, vram_cap)
    return target


def job_priority_key(job: Job) -> tuple[int, float]:
    """Sort key for the inbox queue: lowest priority number first (1 = most
    urgent), then earliest deadline. Deterministic and total."""
    return (job.priority, job.deadline.timestamp())


def order_jobs(jobs: Iterable[Job]) -> list[Job]:
    """Jobs ordered most-urgent-first by (priority, deadline)."""
    return sorted(jobs, key=job_priority_key)


# -- machine probes (side-effecting, best-effort, isolated) ----------------


def cpu_load() -> tuple[int, float]:
    """(cpu_count, 1-minute load average). Falls back to (1, 0.0) where the
    platform does not expose a load average (e.g. Windows)."""
    cpu_count = os.cpu_count() or 1
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):  # pragma: no cover - platform dependent
        load1 = 0.0
    return cpu_count, load1


def free_vram_mb() -> int | None:
    """Free GPU VRAM in MiB via nvidia-smi, or None if unavailable. Best-effort:
    no GPU / no driver / parse error all read as 'unknown' (None)."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, trusted binary
            [exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - env dependent
        return None
    values = [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
    return min(values) if values else None
