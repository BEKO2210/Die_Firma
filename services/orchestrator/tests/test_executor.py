import httpx
import pytest
from conftest import make_job

from die_firma import executor as exec_mod
from die_firma.executor import (
    ClaudeCodeExecutor,
    MockExecutor,
    OllamaExecutor,
    _clean_task,
    _parse_files,
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
    from die_firma.executor import OllamaOptions, SandboxOptions

    assert make_executor("mock").mode == "mock"
    cc = make_executor(
        "claude_code",
        worker_model="m",
        sandbox=SandboxOptions(firejail_bin="firejail", allow_unsandboxed=True),
    )
    assert cc.mode == "claude_code"
    oll = make_executor(
        "ollama",
        ollama=OllamaOptions(url="http://localhost:11434", model="llama3.2"),
    )
    assert oll.mode == "ollama"
    with pytest.raises(ValueError, match="unknown executor mode"):
        make_executor("bogus")


def test_ollama_executor_writes_deliverable_and_tokens(tmp_path):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content)
        # Streamed NDJSON: token chunks then a final done frame with the counts.
        ndjson = (
            '{"response": "print(\'hello "}\n'
            '{"response": "from local model\')"}\n'
            '{"response": "", "prompt_eval_count": 42, "eval_count": 17, "done": true}\n'
        )
        return httpx.Response(200, content=ndjson.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434/", "llama3.2", client=client)
    job = make_job()
    st = Subtask(id="job1:implement", title="Implement", action="implement")
    res = ex.run(job, st, tmp_path)

    assert res.ok is True
    assert res.tokens_in == 42 and res.tokens_out == 17
    assert res.cost_usd == 0.0  # local inference is free
    assert captured["url"].endswith("/api/generate")
    assert captured["body"]["model"] == "llama3.2"
    assert captured["body"]["stream"] is True
    # No file-block in the response -> fallback writes one real file by action.
    written = (tmp_path / "implement.md").read_text(encoding="utf-8")
    assert "hello from local model" in written
    assert "implement.md" in res.artifacts


def test_ollama_executor_streams_progress(tmp_path, monkeypatch):
    import die_firma.executor as ex_mod

    # Make the monotonic clock jump 10s per call so the 1s throttle fires on
    # every token frame -> progress is reported live.
    ticks = iter([0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    monkeypatch.setattr(ex_mod.time, "monotonic", lambda: next(ticks))

    def handler(_request: httpx.Request) -> httpx.Response:
        ndjson = (
            '{"response": "a"}\n{"response": "b"}\n{"response": "c"}\n'
            '{"response": "", "eval_count": 3, "done": true}\n'
        )
        return httpx.Response(200, content=ndjson.encode("utf-8"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434", "llama3.2", client=client)
    deltas: list[int] = []
    res = ex.run(
        make_job(),
        Subtask(id="s", title="t", action="implement"),
        tmp_path,
        progress=lambda _din, dout: deltas.append(dout),
    )
    assert res.tokens_out == 3
    # Every output token surfaced via a live progress callback.
    assert sum(deltas) == 3


def test_ollama_executor_empty_response_is_not_ok(tmp_path):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"response": "  "}))
    )
    ex = OllamaExecutor("http://localhost:11434", "llama3.2", client=client)
    res = ex.run(make_job(), Subtask(id="s1", title="t", action="a"), tmp_path)
    assert res.ok is False  # empty generation -> sentinel retries


def test_ollama_picks_model_per_task_type():
    ex = OllamaExecutor(
        "http://localhost:11434",
        "default-model",
        models={"code_gen": "coder", "data_prep": "general"},
    )
    assert ex.model_for(make_job(type="code_gen")) == "coder"
    assert ex.model_for(make_job(type="data_prep")) == "general"
    # A type without an override falls back to the default model.
    assert ex.model_for(make_job(type="automation")) == "default-model"


def test_ollama_uses_per_type_model_and_reports_it(tmp_path):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"response": "ok", "eval_count": 3})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor(
        "http://localhost:11434", "default-model", client=client, models={"code_gen": "coder"}
    )
    res = ex.run(
        make_job(type="code_gen"),
        Subtask(id="j:implement", title="t", action="implement"),
        tmp_path,
    )
    assert captured["body"]["model"] == "coder"
    assert res.model == "coder"


def test_ollama_self_review_gets_prior_files_in_prompt(tmp_path):
    # Files already in the workdir (from 'implement') must reach 'self_review'.
    (tmp_path / "index.html").write_text("PRIOR WORK XYZ", encoding="utf-8")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"response": "reviewed"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434", "m", client=client)
    st = Subtask(
        id="j:self_review", title="review", action="self_review", depends_on=["j:implement"]
    )
    ex.run(make_job(), st, tmp_path)
    assert "PRIOR WORK XYZ" in captured["body"]["prompt"]
    assert "index.html" in captured["body"]["prompt"]
    assert "Was wurde gemacht" in captured["body"]["prompt"]  # action-specific instruction


def test_ollama_writes_real_files_with_subfolders(tmp_path):
    response = (
        "Here you go:\n"
        "<<<FILE: index.html>>>\n<!doctype html><title>Hi</title>\n<<<END>>>\n"
        "<<<FILE: src/app.js>>>\nconsole.log('hi');\n<<<END>>>\n"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"response": response}))
    )
    ex = OllamaExecutor("http://localhost:11434", "m", client=client)
    res = ex.run(make_job(), Subtask(id="j:implement", title="t", action="implement"), tmp_path)
    assert (tmp_path / "index.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    assert (tmp_path / "src" / "app.js").read_text(encoding="utf-8").strip() == "console.log('hi');"
    assert set(res.artifacts) == {"index.html", "src/app.js"}


def test_parse_files_rejects_path_escapes():
    text = "<<<FILE: ../evil.sh>>>\nrm -rf /\n<<<END>>>\n<<<FILE: ok/clean.txt>>>\nfine\n<<<END>>>"
    files = _parse_files(text)
    assert set(files) == {"ok/clean.txt"}  # parent-escape dropped


def test_parse_files_strips_markdown_fences():
    # Models often wrap file bodies in ```lang fences despite being told not to.
    text = "<<<FILE: index.html>>>\n```html\n<!doctype html><title>x</title>\n```\n<<<END>>>"
    files = _parse_files(text)
    assert files["index.html"].strip() == "<!doctype html><title>x</title>"
    assert "```" not in files["index.html"]


def test_fallback_infers_html_extension(tmp_path):
    html = "<!DOCTYPE html>\n<html><body>Hi</body></html>"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"response": html}))
    )
    ex = OllamaExecutor("http://localhost:11434", "m", client=client)
    res = ex.run(make_job(), Subtask(id="j:implement", title="t", action="implement"), tmp_path)
    assert "implement.html" in res.artifacts
    assert (tmp_path / "implement.html").is_file()


def test_clean_task_collapses_duplicated_title():
    # `new`/the GUI emit `# <title>\n\n<title>` when no description is given.
    assert (
        _clean_task(make_job(body="# Reverse a string\n\nReverse a string")) == "Reverse a string"
    )
    # A real description is preserved alongside the heading.
    assert "Do the work." in _clean_task(make_job(body="# Build a thing\nDo the work."))


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


def test_ollama_cache_replays_artifacts_without_calling_model(tmp_path):
    from die_firma.cache import ResultCache

    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"response": "<h1>hi</h1>", "eval_count": 5})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cache = ResultCache(tmp_path / "cache")
    ex = OllamaExecutor("http://localhost:11434", "m", client=client, cache=cache)
    job = make_job(type="code_gen")
    st = Subtask(id="j:implement", title="t", action="implement")

    first = ex.run(job, st, tmp_path / "wd1")
    assert first.ok and calls["n"] == 1
    # Identical input in a fresh workdir -> served from cache, no second call.
    second = ex.run(job, st, tmp_path / "wd2")
    assert second.ok and calls["n"] == 1
    assert "cache" in second.output
    assert second.artifacts == first.artifacts


def test_ollama_falls_back_to_secondary_model_on_timeout(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        model = _json.loads(request.content)["model"]
        seen.append(model)
        if model == "primary":
            raise httpx.ConnectTimeout("primary down")
        return httpx.Response(200, json={"response": "ok", "eval_count": 3})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434", "primary", client=client, fallback_model="backup")
    res = ex.run(make_job(), Subtask(id="s", title="t", action="implement"), tmp_path)
    assert res.ok and res.model == "backup"
    assert seen == ["primary", "backup"]


def test_ollama_offline_fallback_emits_placeholder(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("server down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434", "m", client=client, offline_fallback=True)
    res = ex.run(make_job(), Subtask(id="s", title="t", action="implement"), tmp_path)
    assert res.ok and res.model == "offline-fallback"
    assert "implement.md" in res.artifacts
    assert "Platzhalter" in (tmp_path / "implement.md").read_text(encoding="utf-8")


def test_ollama_reraises_when_no_fallback_configured(tmp_path):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("server down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ex = OllamaExecutor("http://localhost:11434", "m", client=client)
    with pytest.raises(httpx.ConnectError):
        ex.run(make_job(), Subtask(id="s", title="t", action="implement"), tmp_path)


def test_usage_from_stream():
    stream = (
        '{"type":"assistant","usage":{"input_tokens":10,"output_tokens":4}}\n'
        "not-json\n"
        '{"type":"result","total_cost_usd":0.25,"usage":{"input_tokens":2,"output_tokens":1}}\n'
        "\n"
    )
    tin, tout, cost = _usage_from_stream(stream)
    assert (tin, tout, cost) == (12, 5, 0.25)
