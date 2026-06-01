"""Sentinel: retry with backoff, loop-breaking, and escalation (prompt §1).

Wraps a unit of work in the retry policy. On exhaustion it marks the task
blocked, emits an escalation event (red flag in the dashboard) and fires a
desktop notification.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from .ingest_client import IngestClient
from .notify import notify as default_notify
from .retry import RetryExhausted, RetryPolicy, run_with_retry

T = TypeVar("T")


class Sentinel:
    def __init__(
        self,
        policy: RetryPolicy,
        ingest: IngestClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        notifier: Callable[[str, str], bool] = lambda t, b: default_notify(t, b),
    ) -> None:
        self._policy = policy
        self._ingest = ingest
        self._sleep = sleep
        self._notify = notifier

    def guard(
        self,
        fn: Callable[[int], T],
        *,
        task_id: str,
        subtask_id: str | None = None,
    ) -> T:
        """Run fn under the retry policy. Re-raises RetryExhausted after
        escalating, so the caller can mark the sub-task failed."""

        def on_error(attempt: int, exc: Exception) -> None:
            self._ingest.emit(
                "error",
                task_id=task_id,
                subtask_id=subtask_id,
                agent="sentinel",
                message=f"attempt {attempt}/{self._policy.max_attempts} failed: {exc}",
            )

        try:
            return run_with_retry(fn, self._policy, sleep=self._sleep, on_error=on_error)
        except RetryExhausted as exhausted:
            self._ingest.emit(
                "status_changed",
                task_id=task_id,
                subtask_id=subtask_id,
                agent="sentinel",
                status="blocked",
                message="retries exhausted",
            )
            self._ingest.emit(
                "escalation",
                task_id=task_id,
                subtask_id=subtask_id,
                agent="sentinel",
                message=str(exhausted.last_error),
            )
            self._notify(
                "Die Firma — Task blocked",
                f"Task {task_id} blocked after {exhausted.attempts} attempts.",
            )
            raise
