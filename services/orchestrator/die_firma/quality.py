"""Quality gate: design-system injection, LLM critique and a generate→critique
→refine loop — the piece that was missing (the old "review" only ran a shell
command, so deliverable quality was never actually checked).

Three independent levers, composed by the orchestrator:
  1. design_system_prompt() — injected into the worker prompt for web jobs so the
     first pass already targets a modern, cohesive design (kills the 2005 look).
  2. critique_text() — a reviewer model scores the deliverable against a rubric
     and lists concrete findings (real review, real tokens).
  3. critique_visual() — for web deliverables, render headless (Playwright),
     screenshot it, and let a vision model (llava) judge the actual layout.
Findings from 2+3 feed refine(), which rewrites the files. Pure functions take
an OllamaClient; the orchestrator owns telemetry and the loop count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .executor import _FILE_PROTOCOL, _parse_files, _read_workdir
from .models import Job
from .ollama_client import OllamaClient


def produced_files(workdir: Path) -> dict[str, str]:
    """Files currently in the workdir (the deliverable so far)."""
    return _read_workdir(workdir, max_bytes=20000)


def html_entrypoint(workdir: Path) -> Path | None:
    """The page to render for a visual check: prefer index.html, else any .html."""
    idx = workdir / "index.html"
    if idx.is_file():
        return idx
    for p in sorted(workdir.rglob("*.html")):
        if p.is_file():
            return p
    return None


# --- critique data ------------------------------------------------------


@dataclass
class Finding:
    severity: str  # high | medium | low
    issue: str
    file: str | None = None


@dataclass
class Critique:
    passed: bool
    score: int  # 0-100
    summary: str
    findings: list[Finding] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    source: str = "text"  # text | visual

    def actionable(self, min_severity: str = "medium") -> list[Finding]:
        order = {"high": 3, "medium": 2, "low": 1}
        floor = order.get(min_severity, 2)
        return [f for f in self.findings if order.get(f.severity, 1) >= floor]


def _findings_from(obj: dict[str, Any]) -> list[Finding]:
    out: list[Finding] = []
    for f in obj.get("findings", []) or []:
        if isinstance(f, dict):
            out.append(
                Finding(
                    severity=str(f.get("severity", "medium")).lower(),
                    issue=str(f.get("issue", "")).strip(),
                    file=(str(f["file"]).strip() if f.get("file") else None),
                )
            )
        elif isinstance(f, str):
            out.append(Finding(severity="medium", issue=f.strip()))
    return [f for f in out if f.issue]


def _critique_from_json(
    obj: dict[str, Any], model: str, source: str, tin: int, tout: int
) -> Critique:
    score = int(obj.get("score", 0) or 0)
    findings = _findings_from(obj)
    # Never accept a deliverable that still has a HIGH-severity finding, even if
    # the model self-reports pass=true — the rubric makes a high issue a fail, so
    # enforce it here rather than trusting the model's own verdict.
    has_high = any(f.severity == "high" for f in findings)
    passed = bool(obj.get("pass", score >= 75)) and not has_high
    return Critique(
        passed=passed,
        score=score,
        summary=str(obj.get("summary", "")).strip(),
        findings=findings,
        tokens_in=tin,
        tokens_out=tout,
        model=model,
        source=source,
    )


# --- textual critique ---------------------------------------------------

_RUBRIC = (
    "You are a senior reviewer. Grade the deliverable below against the original "
    "task. Be strict and concrete.\n"
    "Judge: (1) does it implement EVERY concrete item the task names (e.g. each "
    "listed product), (2) correctness/functionality, (3) for web output — modern "
    "visual design, responsiveness, accessibility, real (not dead) interactivity. "
    "Flag as HIGH severity: any <img> tag or external/file image URL (must be inline "
    "SVG/CSS instead), and any visible text NOT in the task's language.\n"
    "Return ONLY a JSON object:\n"
    '{"score": <0-100>, "pass": <true if score>=75 and no high-severity issue>, '
    '"summary": "<one sentence>", "findings": [{"severity":"high|medium|low",'
    '"file":"<path or null>","issue":"<concrete, actionable>"}]}'
)


def critique_text(client: OllamaClient, model: str, job: Job, files: dict[str, str]) -> Critique:
    bundle = "\n\n".join(f"=== {name} ===\n{content}" for name, content in files.items())
    prompt = (
        f"{_RUBRIC}\n\n## Original task\n{job.body.strip()}\n\n"
        f"## Deliverable files\n{bundle[:24000]}"
    )
    try:
        obj, tin, tout = client.generate_json(model, prompt)
    except Exception:  # noqa: BLE001 — never let review crash the job
        return Critique(True, 75, "critique unavailable; passed by default", model=model)
    return _critique_from_json(obj, model, "text", tin, tout)


# --- visual critique (VLM) ---------------------------------------------


def render_screenshot(html_path: Path, out_png: Path, width: int = 1280, height: int = 900) -> bool:
    """Render the page headless and screenshot it. Returns False (never raises)
    if Playwright/the browser is unavailable so the gate degrades gracefully."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(out_png), full_page=True)
            browser.close()
        return out_png.is_file()
    except Exception:  # noqa: BLE001 — rendering is best-effort
        return False


_VISUAL_RUBRIC = (
    "You are a senior UI/UX designer. Look at this screenshot of a rendered web "
    "page for the task below. Judge the ACTUAL visual result: layout balance, "
    "spacing, colour harmony, typography, whether it looks modern and professional "
    "or dated/broken, and any blank areas or missing images.\n"
    "Return ONLY JSON:\n"
    '{"score": <0-100>, "pass": <true if it looks modern and complete>, '
    '"summary":"<one sentence>", "findings":[{"severity":"high|medium|low",'
    '"file":"index.html","issue":"<what to change visually>"}]}'
)


def critique_visual(client: OllamaClient, vision_model: str, job: Job, png: Path) -> Critique:
    from .ollama_client import encode_image

    prompt = f"{_VISUAL_RUBRIC}\n\n## Task\n{job.body.strip()[:1500]}"
    try:
        obj, tin, tout = client.generate_json(vision_model, prompt, images=[encode_image(png)])
    except Exception:  # noqa: BLE001
        return Critique(
            True, 75, "visual critique unavailable", model=vision_model, source="visual"
        )
    return _critique_from_json(obj, vision_model, "visual", tin, tout)


# --- refine -------------------------------------------------------------


def refine(
    client: OllamaClient,
    model: str,
    job: Job,
    files: dict[str, str],
    findings: list[Finding],
    *,
    extra_brief: str = "",
) -> tuple[dict[str, str], int, int]:
    """Rewrite the deliverable fixing `findings`. Returns (new_files, tin, tout).
    Returns the existing files unchanged if the model emits nothing parseable."""
    bundle = "\n\n".join(f"=== {name} ===\n{content}" for name, content in files.items())
    issues = "\n".join(
        f"- [{f.severity}] {f.file + ': ' if f.file else ''}{f.issue}" for f in findings
    )
    prompt = (
        "You are an expert engineer. Fix ALL of the issues below in the deliverable "
        "and re-emit the FULL corrected files using the SAME paths so they overwrite "
        "the originals. Keep everything that already works.\n\n"
        f"## Original task\n{job.body.strip()}\n{extra_brief}\n\n"
        f"## Issues to fix\n{issues}\n\n## Current files\n{bundle[:24000]}\n"
        f"{_FILE_PROTOCOL}"
    )
    try:
        text, tin, tout = client.generate_text(model, prompt, options={"temperature": 0.4})
    except Exception:  # noqa: BLE001 — a transient model error must not abort the gate
        return (files, 0, 0)
    new_files = _parse_files(text)
    return (new_files or files, tin, tout)
