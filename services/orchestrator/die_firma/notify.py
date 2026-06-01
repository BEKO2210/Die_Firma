"""Desktop notification via notify-send (libnotify / Pop!_OS) — prompt §1.

Best-effort: if notify-send is unavailable the call is a no-op so headless
environments (CI, this container) never fail because of it.
"""

from __future__ import annotations

import shutil
import subprocess


def notify(title: str, body: str, *, urgency: str = "critical") -> bool:
    """Send a desktop notification. Returns True if dispatched, else False."""
    binary = shutil.which("notify-send")
    if binary is None:
        return False
    try:
        subprocess.run(  # noqa: S603 — fixed binary, no shell
            [binary, "--urgency", urgency, title, body], check=False
        )
    except OSError:
        return False
    return True
