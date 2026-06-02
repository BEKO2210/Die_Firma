"""Quality gate building blocks: design detection, critique parsing, refine,
and graceful degradation of the headless renderer."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from die_firma import quality as Q
from die_firma.design import design_system_prompt, is_frontend, wants_web
from die_firma.models import Job


def _job(body: str) -> Job:
    return Job(
        id="j1",
        type="code_gen",
        priority=2,
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        deliverable_format="file",
        body=body,
    )


# -- design.py -----------------------------------------------------------


def test_wants_web_and_is_frontend():
    assert wants_web(_job("Build a Webseite for a farm"))
    assert wants_web(_job("plain"), ("index.html",))
    assert not wants_web(_job("a python cli"))
    assert is_frontend(_job("x"), {"index.html": "<html>"})
    assert not is_frontend(_job("a python cli"), {"app.py": "print(1)"})


def test_design_system_prompt_has_key_rules():
    p = design_system_prompt().lower()
    for kw in ("responsive", "palette", "accessibility", "localstorage"):
        assert kw in p


# -- critique parsing ----------------------------------------------------


class _FakeClient:
    def __init__(self, json_obj=None, text=""):
        self._json = json_obj or {}
        self._text = text

    def generate_json(self, model, prompt, *, system=None, images=None):
        return self._json, 11, 7

    def generate_text(self, model, prompt, *, system=None, images=None, options=None):
        return self._text, 21, 9


def test_critique_text_parses_findings_and_pass():
    obj = {
        "score": 88,
        "pass": True,
        "summary": "solid",
        "findings": [
            {"severity": "low", "file": "styles.css", "issue": "minor nit"},
            {"severity": "high", "issue": "broken image"},
            "loose string finding",
        ],
    }
    crit = Q.critique_text(_FakeClient(obj), "m", _job("x"), {"index.html": "<html>"})
    # A HIGH finding forces fail even though the model self-reported pass=true.
    assert not crit.passed
    assert crit.score == 88 and crit.tokens_in == 11
    # medium+ filter keeps the high and the loose (default medium) string, drops the low.
    actionable = crit.actionable("medium")
    assert any(f.severity == "high" for f in actionable)
    assert all(f.severity != "low" for f in actionable)


def test_critique_text_passes_without_high_findings():
    obj = {
        "score": 90,
        "pass": True,
        "summary": "ok",
        "findings": [
            {"severity": "medium", "issue": "tighten spacing"},
        ],
    }
    crit = Q.critique_text(_FakeClient(obj), "m", _job("x"), {"index.html": "<html>"})
    assert crit.passed and crit.score == 90


def test_critique_text_survives_bad_model_output():
    class Boom:
        def generate_json(self, *a, **k):
            raise ValueError("no json")

    crit = Q.critique_text(Boom(), "m", _job("x"), {"a.txt": "hi"})
    assert crit.passed and "unavailable" in crit.summary


def test_refine_writes_parsed_files_else_keeps():
    text = "<<<FILE: index.html>>>\n<h1>fixed</h1>\n<<<END>>>"
    files, tin, tout = Q.refine(_FakeClient(text=text), "m", _job("x"), {"index.html": "old"}, [])
    assert files["index.html"].strip() == "<h1>fixed</h1>" and (tin, tout) == (21, 9)
    # No parseable blocks -> original files returned unchanged.
    same, _, _ = Q.refine(_FakeClient(text="garbage"), "m", _job("x"), {"a": "b"}, [])
    assert same == {"a": "b"}


def test_critique_visual_reads_image(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG\r\n")
    obj = {"score": 70, "pass": False, "summary": "dated", "findings": []}
    crit = Q.critique_visual(_FakeClient(obj), "llava:7b", _job("x"), png)
    assert crit.source == "visual" and crit.score == 70 and not crit.passed


# -- workdir helpers + renderer -----------------------------------------


def test_produced_files_and_html_entrypoint(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("body{}", encoding="utf-8")
    (tmp_path / ".hidden").write_text("x", encoding="utf-8")
    files = Q.produced_files(tmp_path)
    assert set(files) == {"index.html", "styles.css"}  # hidden file skipped
    assert Q.html_entrypoint(tmp_path) == tmp_path / "index.html"
    assert Q.html_entrypoint(tmp_path / "nope") is None


def test_render_screenshot_degrades_when_playwright_missing(tmp_path, monkeypatch):
    # Simulate Playwright not being importable -> returns False, never raises.
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    ok = Q.render_screenshot(tmp_path / "index.html", tmp_path / "out.png")
    assert ok is False
