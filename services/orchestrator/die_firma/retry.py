"""Retry policy: 3 attempts, exponential backoff (2s/4s/8s) — prompt §1.

The backoff schedule is data-driven (from config). Pure helpers here; the
sentinel wires them to real execution. 100% coverage target.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if any(b < 0 for b in self.backoff_seconds):
            raise ValueError("backoff_seconds must be non-negative")

    def delay_before(self, attempt: int) -> float:
        """Delay (seconds) to wait *before* the given 1-based attempt.

        attempt 1 has no preceding wait. For attempts beyond the schedule the
        last value is reused (clamp), so the policy never indexes out of range.
        """
        if attempt <= 1:
            return 0.0
        if not self.backoff_seconds:
            return 0.0
        idx = min(attempt - 2, len(self.backoff_seconds) - 1)
        return self.backoff_seconds[idx]


class RetryExhausted(RuntimeError):
    """All retry attempts failed."""

    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(f"all {attempts} attempts failed: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def run_with_retry(
    fn: Callable[[int], T],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], None],
    on_attempt: Callable[[int], None] | None = None,
    on_error: Callable[[int, Exception], None] | None = None,
) -> T:
    """Call fn(attempt) until it succeeds or attempts are exhausted.

    `sleep` is injected so tests run instantly and deterministically.
    """
    last: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        delay = policy.delay_before(attempt)
        if delay > 0:
            sleep(delay)
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            return fn(attempt)
        except Exception as exc:  # noqa: BLE001 — retry boundary catches broadly
            last = exc
            if on_error is not None:
                on_error(attempt, exc)
    assert last is not None  # max_attempts >= 1 guarantees at least one try
    raise RetryExhausted(policy.max_attempts, last)
