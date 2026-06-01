import pytest

from die_firma.retry import RetryExhausted, RetryPolicy, run_with_retry


def test_policy_validation():
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(0, (1.0,))
    with pytest.raises(ValueError, match="non-negative"):
        RetryPolicy(3, (-1.0,))


def test_delay_before_schedule_and_clamp():
    p = RetryPolicy(5, (2.0, 4.0, 8.0))
    assert p.delay_before(1) == 0.0
    assert p.delay_before(2) == 2.0
    assert p.delay_before(3) == 4.0
    assert p.delay_before(4) == 8.0
    assert p.delay_before(5) == 8.0  # clamps to last
    assert RetryPolicy(3, ()).delay_before(2) == 0.0


def test_run_succeeds_first_try_without_sleeping():
    slept: list[float] = []
    out = run_with_retry(lambda n: "ok", RetryPolicy(3, (2.0,)), sleep=slept.append)
    assert out == "ok"
    assert slept == []


def test_run_retries_then_succeeds():
    slept: list[float] = []
    attempts: list[int] = []
    errors: list[int] = []

    def flaky(n: int) -> str:
        attempts.append(n)
        if n < 3:
            raise RuntimeError("nope")
        return "done"

    out = run_with_retry(
        flaky,
        RetryPolicy(3, (2.0, 4.0)),
        sleep=slept.append,
        on_attempt=lambda n: None,
        on_error=lambda n, e: errors.append(n),
    )
    assert out == "done"
    assert attempts == [1, 2, 3]
    assert slept == [2.0, 4.0]  # before attempt 2 and 3
    assert errors == [1, 2]


def test_run_exhausts():
    with pytest.raises(RetryExhausted) as ei:
        run_with_retry(
            lambda n: (_ for _ in ()).throw(ValueError("boom")),
            RetryPolicy(2, (1.0,)),
            sleep=lambda s: None,
        )
    assert ei.value.attempts == 2
    assert isinstance(ei.value.last_error, ValueError)
