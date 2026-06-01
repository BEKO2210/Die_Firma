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


def test_provision_session_writes_settings_and_env(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    template = tmp_path / "settings.template.json"
    template.write_text('{"cmd": "python3 __HOOKS_DIR__/pre_tool_use.py"}', encoding="utf-8")
    ex = ClaudeCodeExecutor(
        "firejail",
        allow_unsandboxed=True,
        model="m",
        ingest_url="http://127.0.0.1:4321",
        ingest_token="tok-abc",
        hooks_dir=hooks,
        settings_template=template,
    )
    job = make_job()
    st = Subtask(id="s1", title="t", action="implement")
    workdir = tmp_path / "wd"
    workdir.mkdir()
    env = ex._provision_session(job, st, workdir)

    settings = (workdir / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert str(hooks.resolve()) in settings
    assert "__HOOKS_DIR__" not in settings
    assert env["DIE_FIRMA_TASK_ID"] == job.id
    assert env["DIE_FIRMA_SUBTASK_ID"] == "s1"
    assert env["DIE_FIRMA_DASHBOARD_URL"] == "http://127.0.0.1:4321"
    assert env["DIE_FIRMA_INGEST_TOKEN"] == "tok-abc"


def test_provision_session_without_template_still_sets_identity(tmp_path):
    ex = ClaudeCodeExecutor("firejail", allow_unsandboxed=True, model="m")
    env = ex._provision_session(make_job(), Subtask(id="s1", title="t", action="a"), tmp_path)
    assert env["DIE_FIRMA_TASK_ID"]
    assert not (tmp_path / ".claude").exists()


def test_usage_from_stream():
    stream = (
        '{"type":"assistant","usage":{"input_tokens":10,"output_tokens":4}}\n'
        "not-json\n"
        '{"type":"result","total_cost_usd":0.25,"usage":{"input_tokens":2,"output_tokens":1}}\n'
        "\n"
    )
    tin, tout, cost = _usage_from_stream(stream)
    assert (tin, tout, cost) == (12, 5, 0.25)
