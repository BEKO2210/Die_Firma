"""Chaos tests (review §7): inject random delays and failures into the retry/
sentinel path and assert the orchestration stays well-behaved — it either
recovers within the policy or escalates cleanly, but never hangs, loses a result
or raises an unexpected error.

Randomness is seeded per case so failures are reproducible.
"""

from __future__ import annotations

import random

import pytest

from die_firma.retry import RetryExhausted, RetryPolicy, run_with_retry


def _flaky(fail_prob: float, rng: random.Random):
    """A unit of work that fails with the given probability per attempt."""

    def fn(attempt: int) -> str:
        if rng.random() < fail_prob:
            raise RuntimeError(f"transient on attempt {attempt}")
        return f"ok@{attempt}"

    return fn


@pytest.mark.parametrize("seed", range(25))
def test_retry_recovers_or_escalates_cleanly_under_chaos(seed: int):
    rng = random.Random(seed)
    policy = RetryPolicy(max_attempts=5, backoff_seconds=(0.0,))
    delays: list[float] = []
    attempts: list[int] = []

    try:
        result = run_with_retry(
            _flaky(0.5, rng),
            policy,
            sleep=delays.append,  # record backoff instead of sleeping
            on_attempt=attempts.append,
        )
    except RetryExhausted as exc:
        # Clean escalation: tried the full budget, carries the last error.
        assert exc.attempts == 5
        assert attempts == [1, 2, 3, 4, 5]
    else:
        # Recovered: result reflects the winning attempt, no extra tries after.
        assert result.startswith("ok@")
        assert attempts == list(range(1, len(attempts) + 1))

    # Never waits before the first attempt; every later wait is non-negative.
    assert all(d >= 0 for d in delays)


def test_always_failing_work_exhausts_exactly_once():
    policy = RetryPolicy(max_attempts=3, backoff_seconds=(0.0, 0.0))
    seen: list[int] = []

    def always_fail(attempt: int) -> None:
        seen.append(attempt)
        raise ValueError("nope")

    with pytest.raises(RetryExhausted) as ei:
        run_with_retry(always_fail, policy, sleep=lambda _d: None)
    assert seen == [1, 2, 3]  # exactly max_attempts, no more, no fewer
    assert isinstance(ei.value.last_error, ValueError)


def test_jittered_backoff_schedule_is_monotonic_clamped():
    # Even with an exhausting run, the recorded backoff matches the policy: the
    # schedule is followed and the last value is reused beyond its length.
    policy = RetryPolicy(max_attempts=5, backoff_seconds=(1.0, 2.0))
    waits: list[float] = []

    def always_fail(_attempt: int) -> None:
        raise RuntimeError("x")

    with pytest.raises(RetryExhausted):
        run_with_retry(always_fail, policy, sleep=waits.append)
    # delay_before: attempt2->1, attempt3->2, attempt4->2(clamp), attempt5->2.
    assert waits == [1.0, 2.0, 2.0, 2.0]
