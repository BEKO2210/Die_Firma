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
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import Job, Subtask


@dataclass
class ExecResult:
    ok: bool
    output: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    # Relative filename -> content, written into the subtask workdir.
    artifacts: dict[str, str] = field(default_factory=dict)


class Executor(Protocol):
    mode: str

    def run(self, job: Job, subtask: Subtask, workdir: Path) -> ExecResult: ...


class MockExecutor:
    """Deterministic executor. Produces a stable artifact + fixed telemetry so
    the whole pipeline (incl. token/cost projection) is exercised key-free."""

    mode = "mock"

    def run(self, job: Job, subtask: Subtask, workdir: Path) -> ExecResult:
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
) -> Executor:
    """Factory selecting the executor from config.toml's [executor].mode."""
    if mode == "mock":
        return MockExecutor()
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

    def run(self, job: Job, subtask: Subtask, workdir: Path) -> ExecResult:
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
