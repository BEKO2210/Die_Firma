"""Orchestrator quality gate: drives the critique→refine→re-critique loop with
fakes and asserts reviewer token telemetry + that refine rewrote the files."""

from __future__ import annotations

import types

from conftest import FakeIngest, make_job

from die_firma import ollama_client as oc
from die_firma import quality as Q
from die_firma.dispatcher import Dispatcher
from die_firma.orchestrator import Orchestrator
from die_firma.retry import RetryPolicy
from die_firma.runlog import RunLog
from die_firma.sentinel import Sentinel


class _OllamaExec:
    mode = "ollama"


def _cfg(tmp_path):
    return types.SimpleNamespace(
        work=tmp_path / "work",
        outbox=tmp_path / "outbox",
        runlog=tmp_path / "runlog",
        daily_usd_limit=10.0,
        max_parallel=2,
        quality_enabled=True,
        quality_min_score=75,
        quality_max_refine_passes=1,
        quality_visual=False,
        ollama_url="http://x",
        ollama_models={},
        ollama_roles={},
        ollama_model="qwen2.5-coder:14b",
        ollama_escalation_model="deepseek-r1:14b",
    )


def test_quality_gate_critique_refine_recritique(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.runlog.mkdir(parents=True, exist_ok=True)
    ingest = FakeIngest()
    orch = Orchestrator(
        cfg, ingest, _OllamaExec(), Dispatcher(),
        Sentinel(RetryPolicy(1, (0.0,)), ingest, sleep=lambda _s: None),  # type: ignore[arg-type]
    )

    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "index.html").write_text("<html>old</html>", encoding="utf-8")

    monkeypatch.setattr(
        oc, "OllamaClient",
        lambda *a, **k: types.SimpleNamespace(has_model=lambda m: False, close=lambda: None),
    )

    n = {"calls": 0}

    def fake_critique(client, model, job, files):
        n["calls"] += 1
        if n["calls"] == 1:
            return Q.Critique(False, 40, "weak", [Q.Finding("high", "fix it", "index.html")], 5, 3)
        return Q.Critique(True, 90, "great", [], 4, 2)

    def fake_refine(client, model, job, files, findings, *, extra_brief=""):
        (wd / "index.html").write_text("<html>fixed</html>", encoding="utf-8")
        return {"index.html": "<html>fixed</html>\n"}, 30, 10

    monkeypatch.setattr(Q, "critique_text", fake_critique)
    monkeypatch.setattr(Q, "refine", fake_refine)

    job = make_job(body="build a website")
    orch._quality_gate(job, wd, RunLog(cfg.runlog, job.id))

    # critiqued, refined, critiqued again -> passed
    assert n["calls"] == 2
    assert (wd / "index.html").read_text().strip() == "<html>fixed</html>"
    reviewer_tokens = [
        e for e in ingest.events if e["kind"] == "token_usage" and e.get("agent") == "reviewer"
    ]
    assert reviewer_tokens, "reviewer token usage must be emitted"
    assert any(e.get("agent") == "worker" and e["kind"] == "token_usage" for e in ingest.events)


def test_quality_gate_disabled_is_noop(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.quality_enabled = False
    cfg.runlog.mkdir(parents=True, exist_ok=True)
    ingest = FakeIngest()
    orch = Orchestrator(
        cfg, ingest, _OllamaExec(), Dispatcher(),
        Sentinel(RetryPolicy(1, (0.0,)), ingest, sleep=lambda _s: None),  # type: ignore[arg-type]
    )
    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "index.html").write_text("<html></html>", encoding="utf-8")
    orch._quality_gate(make_job(), wd, RunLog(cfg.runlog, "x"))
    assert ingest.events == []  # disabled -> nothing emitted
