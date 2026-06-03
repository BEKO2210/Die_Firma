from pathlib import Path

from die_firma import watch
from die_firma.watch import is_relevant_event, poll_loop, watch_inbox


def test_is_relevant_event_filters_markdown_and_dirs():
    assert is_relevant_event(False, ("inbox/job.md",)) is True
    assert is_relevant_event(False, ("inbox/notes.txt",)) is False
    assert is_relevant_event(True, ("inbox/",)) is False  # directory event
    # moved event: dest path is the .md one
    assert is_relevant_event(False, ("a.tmp", "b.md")) is True


def test_poll_loop_runs_until_max_cycles():
    calls = {"n": 0}
    slept: list[float] = []

    def on_change() -> None:
        calls["n"] += 1

    poll_loop(on_change, poll_interval=2.0, sleep=slept.append, max_cycles=3)
    assert calls["n"] == 3
    assert slept == [2.0, 2.0, 2.0]


def test_poll_loop_stops_on_predicate():
    calls = {"n": 0}

    def on_change() -> None:
        calls["n"] += 1

    # stop() flips true after the first cycle.
    state = {"done": False}

    def stop() -> bool:
        if calls["n"] >= 1:
            state["done"] = True
        return state["done"]

    poll_loop(on_change, poll_interval=0.0, sleep=lambda _s: None, stop=stop)
    assert calls["n"] == 1


def test_watch_inbox_initial_pass_then_polls(tmp_path: Path):
    calls = {"n": 0}
    watch_inbox(
        tmp_path,
        lambda: calls.__setitem__("n", calls["n"] + 1),
        poll_interval=0.0,
        prefer_watchdog=False,  # force the polling fallback
        sleep=lambda _s: None,
        max_cycles=2,
    )
    # 1 initial pass + 2 poll cycles.
    assert calls["n"] == 3


def test_watchdog_available_returns_bool():
    assert isinstance(watch.watchdog_available(), bool)
