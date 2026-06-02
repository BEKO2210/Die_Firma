"""Configuration loading: config.toml (stdlib tomllib) + .env.

Secrets come only from the environment with a startup hardening check
(claude.md §6). config.toml never holds secrets.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .retry import RetryPolicy
from .secrets import check_anthropic_key, check_token


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from `start` to the directory containing config.toml."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config.toml").is_file():
            return candidate
    raise FileNotFoundError("config.toml not found in any parent directory")


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dep). Does not overwrite existing env."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Config:
    root: Path
    inbox: Path
    outbox: Path
    work: Path
    runlog: Path
    state: Path
    poll_interval: float
    dashboard_url: str
    executor_mode: str
    firejail_bin: str
    allow_unsandboxed: bool
    ollama_url: str
    ollama_model: str
    ollama_models: dict[str, str]
    ollama_roles: dict[str, str]
    ollama_escalation_model: str
    ollama_timeout: float
    ollama_fallback_model: str
    offline_fallback: bool
    cache_enabled: bool
    cache_dir: Path
    plugins_dir: Path
    quality_enabled: bool
    quality_min_score: int
    quality_max_refine_passes: int
    quality_visual: bool
    max_parallel: int
    adaptive_parallel: bool
    min_parallel: int
    adaptive_ceiling: int
    vram_per_worker_mb: int
    retry: RetryPolicy
    daily_usd_limit: float
    models: dict[str, str]
    gate_priority: int
    ingest_token: str
    _anthropic_key: str | None = field(default=None, repr=False)

    def get_anthropic_key(self) -> str:
        """Validated Anthropic key; raises if missing/invalid (called lazily,
        only when the claude_code executor or an SDK agent actually needs it)."""
        return check_anthropic_key(self._anthropic_key)


def load_config(start: Path | None = None) -> Config:
    root = find_repo_root(start)
    load_dotenv(root / ".env")
    with (root / "config.toml").open("rb") as fh:
        raw = tomllib.load(fh)

    general = raw["general"]
    retry_raw = raw["retry"]
    ollama_raw = raw.get("ollama", {})
    quality_raw = raw.get("quality", {})
    cache_raw = raw.get("cache", {})

    def p(name: str) -> Path:
        return (root / str(general[name])).resolve()

    return Config(
        root=root,
        inbox=p("inbox_dir"),
        outbox=p("outbox_dir"),
        work=p("work_dir"),
        runlog=p("runlog_dir"),
        state=p("state_dir"),
        poll_interval=float(general["poll_interval_seconds"]),
        dashboard_url=os.environ.get("DIE_FIRMA_DASHBOARD_URL", raw["dashboard"]["url"]).rstrip(
            "/"
        ),
        # Env override lets CI / the demo / tests force "mock" without editing
        # config.toml (which defaults to local "ollama").
        executor_mode=os.environ.get("DIE_FIRMA_EXECUTOR_MODE", raw["executor"]["mode"]),
        firejail_bin=raw["executor"]["firejail_bin"],
        allow_unsandboxed=bool(raw["executor"]["allow_unsandboxed"]),
        ollama_url=os.environ.get(
            "DIE_FIRMA_OLLAMA_URL", str(ollama_raw.get("url", "http://localhost:11434"))
        ).rstrip("/"),
        ollama_model=os.environ.get(
            "DIE_FIRMA_OLLAMA_MODEL", str(ollama_raw.get("model", "llama3.2"))
        ),
        # Per-task-type model overrides from [ollama.models]; the worker picks
        # the best installed model for each job type (code vs. general, …).
        ollama_models={str(k): str(v) for k, v in dict(ollama_raw.get("models", {})).items()},
        # Per-role overrides from [ollama.roles] + the retry escalation model.
        ollama_roles={str(k): str(v) for k, v in dict(ollama_raw.get("roles", {})).items()},
        ollama_escalation_model=str(ollama_raw.get("escalation_model", "deepseek-r1:14b")),
        # Per-request timeout + offline resilience (review §4).
        ollama_timeout=float(
            os.environ.get("DIE_FIRMA_OLLAMA_TIMEOUT", ollama_raw.get("timeout_seconds", 600.0))
        ),
        ollama_fallback_model=str(ollama_raw.get("fallback_model", "")),
        offline_fallback=bool(ollama_raw.get("offline_fallback", False)),
        # Result cache (review §3) — content-addressed under state/.
        cache_enabled=bool(cache_raw.get("enabled", True)),
        cache_dir=(root / str(cache_raw.get("dir", "state/cache"))).resolve(),
        # Task plugin discovery directory (review §1).
        plugins_dir=(root / str(raw.get("plugins", {}).get("dir", "tasks"))).resolve(),
        quality_enabled=bool(quality_raw.get("enabled", True)),
        quality_min_score=int(quality_raw.get("min_score", 75)),
        quality_max_refine_passes=int(quality_raw.get("max_refine_passes", 2)),
        quality_visual=bool(quality_raw.get("visual", True)),
        max_parallel=int(raw["concurrency"]["max_parallel_tasks"]),
        # Adaptive parallelism (review §2): size the worker pool to the machine.
        adaptive_parallel=bool(raw["concurrency"].get("adaptive", False)),
        min_parallel=int(raw["concurrency"].get("min_parallel", 1)),
        adaptive_ceiling=int(
            raw["concurrency"].get("adaptive_ceiling", raw["concurrency"]["max_parallel_tasks"])
        ),
        vram_per_worker_mb=int(raw["concurrency"].get("vram_per_worker_mb", 0)),
        retry=RetryPolicy(
            max_attempts=int(retry_raw["max_attempts"]),
            backoff_seconds=tuple(float(x) for x in retry_raw["backoff_seconds"]),
        ),
        daily_usd_limit=float(raw["cost"]["daily_usd_limit"]),
        models=dict(raw["models"]),
        gate_priority=int(raw["approval"]["gate_priority"]),
        ingest_token=check_token(
            os.environ.get("DIE_FIRMA_INGEST_TOKEN"), name="DIE_FIRMA_INGEST_TOKEN"
        ),
        _anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
