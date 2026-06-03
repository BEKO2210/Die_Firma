"""Inbox watching: react to filesystem changes instead of busy-polling (review §4).

The classic loop re-scanned ``inbox/`` every ``poll_interval`` seconds. With
``watchdog`` installed we instead get native OS notifications (inotify on Linux),
so a new job is picked up immediately with no wasted CPU. A periodic safety
re-scan still runs (events can be missed on some filesystems), and if
``watchdog`` is unavailable we fall back to pure polling — correctness either way.

The decision logic and event filter are pure helpers so they stay unit-testable
without real filesystem events; the Observer wiring is the only untested seam.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

# How many poll_intervals between safety re-scans on the watchdog path.
_SAFETY_SCAN_MULTIPLIER = 15


def watchdog_available() -> bool:
    """Whether the optional ``watchdog`` dependency is importable."""
    try:
        import watchdog.events  # noqa: F401
        import watchdog.observers  # noqa: F401
    except ImportError:
        return False
    return True


def is_relevant_event(is_directory: bool, paths: tuple[str, ...]) -> bool:
    """True if a filesystem event touches a Markdown job file (not a directory)."""
    if is_directory:
        return False
    return any(p.endswith(".md") for p in paths)


def poll_loop(
    on_change: Callable[[], None],
    *,
    poll_interval: float,
    sleep: Callable[[float], None] = time.sleep,
    stop: Callable[[], bool] | None = None,
    max_cycles: int | None = None,
) -> None:
    """The guaranteed fallback: sleep, then re-scan, until ``stop`` or ``max_cycles``."""
    cycles = 0
    while stop is None or not stop():
        sleep(poll_interval)
        on_change()
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break


def _watch_with_watchdog(  # pragma: no cover - needs real FS events / OS observer
    inbox_dir: Path,
    on_change: Callable[[], None],
    *,
    poll_interval: float,
    stop: Callable[[], bool] | None,
) -> None:
    """Event-driven watch via watchdog, with a periodic safety re-scan."""
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    def _as_str(p: object) -> str:
        if isinstance(p, (bytes, bytearray)):
            return p.decode("utf-8", "ignore")
        return str(p)

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            raw = (event.src_path, getattr(event, "dest_path", ""))
            paths = tuple(_as_str(p) for p in raw if p)
            if is_relevant_event(event.is_directory, paths):
                on_change()

    inbox_dir.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(_Handler(), str(inbox_dir), recursive=False)
    observer.start()
    try:
        safety_gap = poll_interval * _SAFETY_SCAN_MULTIPLIER
        while stop is None or not stop():
            time.sleep(safety_gap)
            on_change()  # safety re-scan in case an event was missed
    finally:
        observer.stop()
        observer.join()


def watch_inbox(
    inbox_dir: Path,
    on_change: Callable[[], None],
    *,
    poll_interval: float,
    prefer_watchdog: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    stop: Callable[[], bool] | None = None,
    max_cycles: int | None = None,
) -> None:
    """Process the inbox once, then keep processing on change.

    Uses watchdog when available (and ``prefer_watchdog``), otherwise polls. Any
    watchdog setup failure degrades to polling so the loop never dies silently.
    """
    on_change()  # initial pass so existing jobs are handled immediately
    if prefer_watchdog and watchdog_available():
        try:
            _watch_with_watchdog(inbox_dir, on_change, poll_interval=poll_interval, stop=stop)
            return
        except Exception:  # noqa: BLE001 - any observer failure -> safe polling fallback
            pass
    poll_loop(
        on_change,
        poll_interval=poll_interval,
        sleep=sleep,
        stop=stop,
        max_cycles=max_cycles,
    )
