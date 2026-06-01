"""Tests for the Claude Code worker hooks (hooks/ is not a package, so it is
added to sys.path explicitly)."""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parents[3] / "hooks"


@pytest.fixture
def common(monkeypatch):
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    mod = importlib.import_module("common")
    return importlib.reload(mod)


def test_emit_posts_identity_and_fields(common, monkeypatch):
    sent: dict = {}

    def fake_post(payload):
        sent.update(payload)

    monkeypatch.setattr(common, "_post", fake_post)
    monkeypatch.setenv("DIE_FIRMA_TASK_ID", "t1")
    monkeypatch.setenv("DIE_FIRMA_SUBTASK_ID", "s1")
    common.emit("tool_call_start", message="Bash", tokens_in=None)
    assert sent["kind"] == "tool_call_start"
    assert sent["agent"] == "worker"
    assert sent["task_id"] == "t1"
    assert sent["subtask_id"] == "s1"
    assert sent["message"] == "Bash"
    assert "tokens_in" not in sent  # None fields dropped


def test_emit_swallows_errors(common, monkeypatch, capsys):
    def boom(_payload):
        raise OSError("network down")

    monkeypatch.setattr(common, "_post", boom)
    common.emit("log", message="x")  # must not raise
    assert "ingest failed" in capsys.readouterr().err


def test_read_hook_input(common, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"tool_name": "Edit"}'))
    assert common.read_hook_input() == {"tool_name": "Edit"}
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert common.read_hook_input() == {}
    monkeypatch.setattr("sys.stdin", io.StringIO("[1,2,3]"))
    assert common.read_hook_input() == {}  # non-dict -> {}


def test_hook_scripts_emit(monkeypatch):
    """Each hook script runs end-to-end with a stubbed emit."""
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    common = importlib.reload(importlib.import_module("common"))
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(common, "_post", lambda payload: calls.append((payload["kind"], payload)))
    for script, stdin in (
        ("pre_tool_use", '{"tool_name":"Bash"}'),
        ("post_tool_use", '{"tool_name":"Bash","tool_response":{"error":"x"}}'),
        ("stop", "{}"),
        ("subagent_stop", "{}"),
    ):
        sys.modules.pop(script, None)
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        mod = importlib.import_module(script)
        assert mod.main() == 0
    kinds = [c[0] for c in calls]
    assert kinds == ["tool_call_start", "tool_call_end", "log", "log"]
