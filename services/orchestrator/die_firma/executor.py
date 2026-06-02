"""Executor abstraction: `mock | claude_code` (prompt §1).

- mock: deterministic, no API key — powers tests and the full mock E2E.
- claude_code: spawns `claude -p ... --output-format stream-json` under
  firejail with a path whitelist, so native Claude Code hooks emit telemetry.

The firejail command is built by a pure function so it can be unit-tested
without a sandbox present.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Called during generation with (tokens_in_delta, tokens_out_delta) so the
# orchestrator can stream live token telemetry instead of one event per call.
ProgressFn = Callable[[int, int], None]

import httpx

from .models import Job, Subtask


@dataclass
class ExecResult:
    ok: bool
    output: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    # Which model produced this result (for telemetry + the deliverable summary).
    model: str = ""
    # Relative path -> content for every file written into the subtask workdir.
    artifacts: dict[str, str] = field(default_factory=dict)


class Executor(Protocol):
    mode: str

    def run(
        self,
        job: Job,
        subtask: Subtask,
        workdir: Path,
        attempt: int = 1,
        progress: ProgressFn | None = None,
    ) -> ExecResult: ...


class MockExecutor:
    """Deterministic executor. Produces a stable artifact + fixed telemetry so
    the whole pipeline (incl. token/cost projection) is exercised key-free."""

    mode = "mock"

    def run(
        self,
        job: Job,
        subtask: Subtask,
        workdir: Path,
        attempt: int = 1,
        progress: ProgressFn | None = None,
    ) -> ExecResult:
        workdir.mkdir(parents=True, exist_ok=True)
        filename = f"{subtask.id}.txt"
        content = (
            f"# mock output\njob={job.id}\ntype={job.type}\n"
            f"subtask={subtask.id}\naction={subtask.action}\n"
        )
        (workdir / filename).write_text(content, encoding="utf-8")
        return ExecResult(
            ok=True,
            output=f"[mock] {subtask.action} for {subtask.id}",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.001,
            artifacts={filename: content},
        )


def make_executor(
    mode: str,
    *,
    firejail_bin: str,
    allow_unsandboxed: bool,
    worker_model: str,
    ingest_url: str | None = None,
    ingest_token: str | None = None,
    hooks_dir: Path | None = None,
    settings_template: Path | None = None,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2",
    ollama_models: dict[str, str] | None = None,
    ollama_roles: dict[str, str] | None = None,
    ollama_escalation_model: str = "deepseek-r1:14b",
) -> Executor:
    """Factory selecting the executor from config.toml's [executor].mode."""
    if mode == "mock":
        return MockExecutor()
    if mode == "ollama":
        from .router import Router

        router = Router(
            per_type=dict(ollama_models or {}),
            roles=dict(ollama_roles or {}),
            default_model=ollama_model,
            escalation_model=ollama_escalation_model,
        )
        return OllamaExecutor(ollama_url, ollama_model, models=ollama_models, router=router)
    if mode == "claude_code":
        return ClaudeCodeExecutor(
            firejail_bin,
            allow_unsandboxed,
            worker_model,
            ingest_url=ingest_url,
            ingest_token=ingest_token,
            hooks_dir=hooks_dir,
            settings_template=settings_template,
        )
    raise ValueError(f"unknown executor mode: {mode!r}")


def build_firejail_command(
    firejail_bin: str,
    claude_bin: str,
    prompt: str,
    workdir: Path,
    allowed_paths: list[str],
    model: str,
) -> list[str]:
    """Construct the sandboxed Claude Code invocation (pure, testable).

    The worker can only see its own workdir plus explicitly whitelisted paths
    (prompt §7). Output is stream-json so native hooks feed telemetry.
    """
    cmd = [
        firejail_bin,
        "--quiet",
        "--noprofile",
        f"--whitelist={workdir}",
    ]
    cmd += [f"--whitelist={p}" for p in allowed_paths]
    cmd += [
        "--",
        claude_bin,
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "stream-json",
    ]
    return cmd


def _usage_from_stream(stdout: str) -> tuple[int, int, float]:
    """Sum token usage / cost from a stream-json transcript (best-effort)."""
    tin = tout = 0
    cost = 0.0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        usage = obj.get("usage") if isinstance(obj, dict) else None
        if isinstance(usage, dict):
            tin += int(usage.get("input_tokens", 0) or 0)
            tout += int(usage.get("output_tokens", 0) or 0)
        if isinstance(obj, dict) and isinstance(obj.get("total_cost_usd"), (int, float)):
            cost = float(obj["total_cost_usd"])
    return tin, tout, cost


class ClaudeCodeExecutor:
    """Runs a worker as headless Claude Code under firejail. Fail-closed when
    firejail is missing unless explicitly allowed to run unsandboxed."""

    mode = "claude_code"

    def __init__(
        self,
        firejail_bin: str,
        allow_unsandboxed: bool,
        model: str,
        claude_bin: str = "claude",
        *,
        ingest_url: str | None = None,
        ingest_token: str | None = None,
        hooks_dir: Path | None = None,
        settings_template: Path | None = None,
    ) -> None:
        self._firejail = firejail_bin
        self._allow_unsandboxed = allow_unsandboxed
        self._model = model
        self._claude = claude_bin
        self._ingest_url = ingest_url
        self._ingest_token = ingest_token
        self._hooks_dir = hooks_dir
        self._settings_template = settings_template

    def _build(self, prompt: str, workdir: Path, allowed_paths: list[str]) -> list[str]:
        have_firejail = shutil.which(self._firejail) is not None
        if not have_firejail:
            if not self._allow_unsandboxed:
                raise RuntimeError(
                    f"firejail ({self._firejail!r}) not found and allow_unsandboxed is false"
                )
            return [
                self._claude,
                "-p",
                prompt,
                "--model",
                self._model,
                "--output-format",
                "stream-json",
            ]
        return build_firejail_command(
            self._firejail, self._claude, prompt, workdir, allowed_paths, self._model
        )

    def _provision_session(self, job: Job, subtask: Subtask, workdir: Path) -> dict[str, str]:
        """Write .claude/settings.json from the template (so the worker's hooks
        fire) and return the identity/ingest env the hooks need."""
        if self._settings_template is not None and self._hooks_dir is not None:
            try:
                tmpl = self._settings_template.read_text(encoding="utf-8")
                settings = tmpl.replace("__HOOKS_DIR__", str(self._hooks_dir.resolve()))
                claude_dir = workdir / ".claude"
                claude_dir.mkdir(parents=True, exist_ok=True)
                (claude_dir / "settings.json").write_text(settings, encoding="utf-8")
            except OSError:  # pragma: no cover - filesystem edge
                pass
        env = dict(os.environ)
        env["DIE_FIRMA_TASK_ID"] = job.id
        env["DIE_FIRMA_SUBTASK_ID"] = subtask.id
        if self._ingest_url is not None:
            env["DIE_FIRMA_DASHBOARD_URL"] = self._ingest_url
        if self._ingest_token is not None:
            env["DIE_FIRMA_INGEST_TOKEN"] = self._ingest_token
        return env

    def run(
        self,
        job: Job,
        subtask: Subtask,
        workdir: Path,
        attempt: int = 1,
        progress: ProgressFn | None = None,
    ) -> ExecResult:
        workdir.mkdir(parents=True, exist_ok=True)
        env = self._provision_session(job, subtask, workdir)
        prompt = (
            f"You are the worker agent. Job {job.id} ({job.type}). "
            f"Sub-task {subtask.id}: {subtask.title}\n\n{job.body}\n\n"
            f"Action: {subtask.action}. Write results into the working directory."
        )
        cmd = self._build(prompt, workdir, job.allowed_paths)
        proc = subprocess.run(  # noqa: S603 — cmd is built from trusted config
            cmd, cwd=workdir, capture_output=True, text=True, check=False, env=env
        )
        tin, tout, cost = _usage_from_stream(proc.stdout)
        return ExecResult(
            ok=proc.returncode == 0,
            output=proc.stdout if proc.returncode == 0 else proc.stderr,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=cost,
        )


# Concrete, action-specific instructions so each sub-task does exactly one job
# well and emits REAL files (not one .md blob), keyed by Subtask.action.
_ACTION_INSTRUCTIONS: dict[str, str] = {
    "implement": (
        "Produce the COMPLETE, working deliverable as REAL FILES with correct "
        "extensions and a sensible folder structure — e.g. `index.html` + "
        "`styles.css` + `script.js` for a web page, `app.py` for Python, or a "
        "`package.json` plus a `src/` tree for a Node/React app. Emit every file "
        "the deliverable needs. Never cram everything into a single .md file."
    ),
    "self_review": (
        "Review the files produced in the previous step (shown above) for "
        "correctness, completeness and quality. Fix every issue, then re-emit the "
        "FINAL corrected files IN FULL using the SAME paths so they overwrite the "
        "drafts. Also emit a file `NOTES.md` whose body is a '## Was wurde gemacht' "
        "section with 2–4 bullets stating exactly what was built and what you changed."
    ),
    "analyze": (
        "Analyze the target and emit a structured review report as `REVIEW.md`: "
        "concrete findings, a severity for each, and actionable recommendations."
    ),
    "build_script": (
        "Write the complete, runnable automation script as a real file with the "
        "right extension (e.g. `automate.py`, `script.sh`) plus a short `README.md` "
        "explaining usage and prerequisites."
    ),
    "smoke": (
        "Smoke-test the script from the previous step: walk through how it runs and "
        "the expected output, and flag any bug or missing case. Emit your findings "
        "and a clear PASS or FAIL verdict as `SMOKE_TEST.md`."
    ),
    "ingest": (
        "Ingest and validate the input data described in the task. Emit `INGEST.md` "
        "stating your assumptions, the detected schema, and any data-quality issues."
    ),
    "transform": (
        "Using the data from the previous step, emit the FINAL requested data file "
        "with the correct extension (e.g. `.csv`, `.json`)."
    ),
}

# Strict, fence-free file protocol the model must use so we can write real files.
_FILE_PROTOCOL = (
    "\n## Output format (STRICT — follow exactly)\n"
    "Return the deliverable as one or more real files. For EACH file emit a block:\n"
    "<<<FILE: relative/path/name.ext>>>\n"
    "...the full file content...\n"
    "<<<END>>>\n"
    "Rules: pick correct extensions; create sub-folders via the path (e.g. "
    "src/App.jsx); do NOT wrap file contents in markdown code fences; emit every "
    "file the deliverable needs."
)

_FILE_BLOCK = re.compile(
    r"<<<FILE:\s*(?P<path>[^\n>]+?)\s*>>>\r?\n(?P<body>.*?)\r?\n?<<<END>>>",
    re.DOTALL,
)

_LANG_EXT: dict[str, str] = {
    "python": "py",
    "py": "py",
    "html": "html",
    "htm": "html",
    "css": "css",
    "javascript": "js",
    "js": "js",
    "jsx": "jsx",
    "typescript": "ts",
    "ts": "ts",
    "tsx": "tsx",
    "json": "json",
    "bash": "sh",
    "sh": "sh",
    "shell": "sh",
    "sql": "sql",
    "yaml": "yaml",
    "yml": "yml",
    "markdown": "md",
    "md": "md",
    "text": "txt",
    "": "txt",
}


def _clean_task(job: Job) -> str:
    """The task text without the duplicated title that `new`/the GUI emit.

    Inbox bodies look like `# <title>\\n\\n<description>`, and when no description
    is given the description IS the title — feeding both to the model made it ask
    'why did you repeat the same text twice?'. Collapse that here."""
    body = job.body.strip()
    if not body:
        return job.id
    lines = body.splitlines()
    first = lines[0].lstrip()
    if first.startswith("#"):
        heading = first.lstrip("#").strip()
        rest = "\n".join(lines[1:]).strip()
        if not rest or rest == heading:
            return heading
        return f"{heading}\n\n{rest}"
    return body


def _safe_relpath(raw: str) -> str | None:
    """A sandbox-safe relative path: no absolutes, no parent escapes."""
    p = raw.strip().strip("/").replace("\\", "/")
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if not parts or any(seg == ".." for seg in parts):
        return None
    return "/".join(parts)


def _strip_fence(body: str) -> tuple[str, str | None]:
    """Drop a wrapping ```lang … ``` fence models add despite being told not to.

    Returns (clean_body, language_or_None)."""
    b = body.strip("\n")
    full = re.match(r"^```([\w+-]*)[^\n]*\n(.*)\n```\s*$", b, re.DOTALL)
    if full:
        return full.group(2), full.group(1).lower() or None
    # Tolerate a leading fence whose close was dropped (model truncation).
    lead = re.match(r"^```([\w+-]*)[^\n]*\n(.*)$", b, re.DOTALL)
    if lead:
        rest = lead.group(2)
        if rest.rstrip().endswith("```"):
            rest = rest.rstrip()[:-3].rstrip("\n")
        return rest, lead.group(1).lower() or None
    return b, None


def _parse_files(text: str) -> dict[str, str]:
    """Extract `<<<FILE: path>>> ... <<<END>>>` blocks into {relpath: content}."""
    files: dict[str, str] = {}
    for m in _FILE_BLOCK.finditer(text):
        rel = _safe_relpath(m.group("path"))
        if rel is not None:
            body, _ = _strip_fence(m.group("body"))
            files[rel] = body.strip("\n") + "\n"
    return files


def _fallback_file(text: str, subtask: Subtask) -> dict[str, str]:
    """No file blocks emitted — infer a single sensible file from the raw output."""
    body, lang = _strip_fence(text.strip())
    if lang is not None:
        ext = _LANG_EXT.get(lang, "txt")
    elif "<!doctype html" in body.lower() or "<html" in body.lower():
        ext = "html"
    else:
        ext = "md"
    return {f"{subtask.action}.{ext}": body.strip("\n") + "\n"}


def _read_workdir(workdir: Path, max_bytes: int = 8000) -> dict[str, str]:
    """Files already produced in the workdir, so dependent steps build on real
    prior work (e.g. self_review sees exactly what implement wrote)."""
    ctx: dict[str, str] = {}
    if not workdir.is_dir():
        return ctx
    for path in sorted(workdir.rglob("*")):
        rel = path.relative_to(workdir)
        if path.is_file() and ".git" not in rel.parts and not path.name.startswith("."):
            try:
                ctx[str(rel)] = path.read_text(encoding="utf-8")[:max_bytes]
            except (OSError, UnicodeDecodeError):
                continue
    return ctx


def _worker_prompt(job: Job, subtask: Subtask, context: dict[str, str]) -> str:
    task = _clean_task(job)
    instr = _ACTION_INSTRUCTIONS.get(subtask.action, "Produce the deliverable for this step.")
    parts = [
        "You are an expert software engineer in an autonomous build pipeline. "
        "Work precisely and decisively — you have everything you need, so never ask "
        "the user questions and never apologise.",
        f"\n## Task\n{task}",
    ]
    if context:
        joined = "\n\n".join(
            f"### File `{name}` from a previous step:\n{content}"
            for name, content in context.items()
        )
        parts.append(
            "\n## Files already produced (build on these — re-emit to change them)\n" + joined
        )
    parts.append(f"\n## Your job for this '{subtask.action}' step\n{instr}")
    # Web jobs get the full design-system brief so the very first pass already
    # targets a modern, cohesive result instead of a bare template.
    from .design import design_system_prompt, wants_web

    if wants_web(job, tuple(context)):
        parts.append(design_system_prompt())
    parts.append(_FILE_PROTOCOL)
    return "\n".join(parts)


class OllamaExecutor:
    """Runs the worker against a LOCAL Ollama server — no API key, no cloud.

    Talks to Ollama's HTTP API (`POST /api/generate`). The generated text is
    written into the sub-task workdir as the deliverable; token counts come from
    Ollama's `prompt_eval_count` / `eval_count`. Local inference is free, so
    cost is always 0 (the daily cost guard simply never trips).

    The model is chosen per job type from `models` (e.g. a code model for
    code_gen, a general model for data_prep), falling back to the default."""

    mode = "ollama"

    def __init__(
        self,
        url: str,
        model: str,
        client: httpx.Client | None = None,
        timeout: float = 600.0,
        *,
        models: dict[str, str] | None = None,
        router: "object | None" = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._default_model = model
        self._models = dict(models or {})
        self._client = client or httpx.Client(timeout=timeout)
        if router is None:
            from .router import Router

            router = Router(per_type=self._models, default_model=model)
        self._router = router

    def model_for(self, job: Job, subtask: Subtask | None = None, attempt: int = 1) -> str:
        """Best available model for this step (routes by role + escalation)."""
        if subtask is None:
            return self._models.get(job.type, self._default_model)
        return self._router.model_for(job, subtask, attempt)

    def run(
        self,
        job: Job,
        subtask: Subtask,
        workdir: Path,
        attempt: int = 1,
        progress: ProgressFn | None = None,
    ) -> ExecResult:
        workdir.mkdir(parents=True, exist_ok=True)
        model = self.model_for(job, subtask, attempt)
        context = _read_workdir(workdir)
        prompt = _worker_prompt(job, subtask, context)
        text, tin, tout = self._generate(model, prompt, progress)
        # Write the deliverable as REAL files (with sub-folders), not one .md blob.
        files = _parse_files(text) or _fallback_file(text, subtask)
        for rel, content in files.items():
            dest = workdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        return ExecResult(
            ok=bool(text.strip()) and bool(files),
            output=text[:500],
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=0.0,  # local inference is free
            model=model,
            artifacts=files,
        )

    def _generate(
        self, model: str, prompt: str, progress: ProgressFn | None
    ) -> tuple[str, int, int]:
        """Stream /api/generate so token throughput is observable live. Batches
        roughly one progress callback per second with the count of new output
        tokens; returns (full_text, prompt_tokens, output_tokens). Falls back
        gracefully — a non-streamed single-object response parses as one chunk."""
        parts: list[str] = []
        tin = tout = 0
        since = 0
        last = time.monotonic()
        with self._client.stream(
            "POST",
            f"{self._url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": True},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = obj.get("response", "")
                if piece:
                    parts.append(piece)
                    since += 1
                if obj.get("done"):
                    tin = int(obj.get("prompt_eval_count", 0) or 0)
                    tout = int(obj.get("eval_count", 0) or 0)
                now = time.monotonic()
                if progress is not None and since and (now - last) >= 1.0:
                    progress(0, since)
                    since = 0
                    last = now
        return "".join(parts), tin, tout
