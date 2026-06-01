from die_firma import notify as notify_mod
from die_firma.notify import notify


def test_noop_when_binary_missing(monkeypatch):
    monkeypatch.setattr(notify_mod.shutil, "which", lambda _b: None)
    assert notify("t", "b") is False


def test_dispatches_when_present(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(notify_mod.shutil, "which", lambda _b: "/usr/bin/notify-send")
    monkeypatch.setattr(notify_mod.subprocess, "run", lambda *a, **k: calls.append(a[0]))
    assert notify("Title", "Body") is True
    assert calls and calls[0][0] == "/usr/bin/notify-send"


def test_handles_oserror(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("nope")

    monkeypatch.setattr(notify_mod.shutil, "which", lambda _b: "/usr/bin/notify-send")
    monkeypatch.setattr(notify_mod.subprocess, "run", boom)
    assert notify("t", "b") is False
