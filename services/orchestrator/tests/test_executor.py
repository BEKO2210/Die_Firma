import pytest
from conftest import make_job

from die_firma import executor as exec_mod
from die_firma.executor import (
    ClaudeCodeExecutor,
    MockExecutor,
    _usage_from_stream,
    build_firejail_command,
    make_executor,
)
from die_firma.models import Subtask


def test_build_firejail_command(tmp_path):
    cmd = build_firejail_command(
        "firejail", "claude", "do it", tmp_path, ["/extra/path"], "claude-opus-4-8"
    )
    assert cmd[0] == "firejail"
    assert f"--whitelist={tmp_path}" in cmd
    assert "--whitelist=/extra/path" in cmd
    assert cmd[cmd.index("--") + 1] == "claude"
    assert "stream-json" in cmd
    assert "claude-opus-4-8" in cmd


def test_mock_executor_writes_artifact_and_telemetry(tmp_path):
    job = make_job()
    st = Subtask(id="s1", title="t", action="implement")
    res = MockExecutor().run(job, st, tmp_path)
    assert res.ok
    assert (tmp_path / "s1.txt").is_file()
    assert res.tokens_in == 100 and res.tokens_out == 50
    assert res.cost_usd == pytest.approx(0.001)
    assert "s1.txt" in res.artifacts


def test_make_executor():
    assert (
        make_executor(
            "mock", firejail_bin="firejail", allow_unsandboxed=False, worker_model="m"
        ).mode
        == "mock"
    )
    cc = make_executor(
        "claude_code", firejail_bin="firejail", allow_unsandboxed=True, worker_model="m"
    )
    assert cc.mode == "claude_code"
    with pytest.raises(ValueError, match="unknown executor mode"):
        make_executor("bogus", firejail_bin="firejail", allow_unsandboxed=False, worker_model="m")


def test_claude_executor_fail_closed_without_firejail(monkeypatch, tmp_path):
    monkeypatch.setattr(exec_mod.shutil, "which", lambda _b: None)
    ex = ClaudeCodeExecutor("firejail", allow_unsandboxed=False, model="m")
    with pytest.raises(RuntimeError, match="not found"):
        ex._build("p", tmp_path, [])
    # When explicitly allowed, falls back to an unsandboxed command.
    ex2 = ClaudeCodeExecutor("firejail", allow_unsandboxed=True, model="m")
    cmd = ex2._build("p", tmp_path, [])
    assert cmd[0] == "claude"


def test_claude_executor_builds_sandboxed_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(exec_mod.shutil, "which", lambda _b: "/usr/bin/firejail")
    ex = ClaudeCodeExecutor("firejail", allow_unsandboxed=False, model="m")
    cmd = ex._build("p", tmp_path, ["/x"])
    assert cmd[0] == "firejail"


def test_usage_from_stream():
    stream = (
        '{"type":"assistant","usage":{"input_tokens":10,"output_tokens":4}}\n'
        "not-json\n"
        '{"type":"result","total_cost_usd":0.25,"usage":{"input_tokens":2,"output_tokens":1}}\n'
        "\n"
    )
    tin, tout, cost = _usage_from_stream(stream)
    assert (tin, tout, cost) == (12, 5, 0.25)
