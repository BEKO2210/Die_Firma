"""CLI: submit | approve | status | reset | run (prompt §2).

Builds the orchestrator from config.toml + .env and drives the inbox.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .cache import ResultCache
from .config import Config, load_config
from .dispatcher import Dispatcher
from .executor import make_executor
from .ingest_client import IngestClient
from .models import DELIVERABLE_FORMATS, TASK_TYPES
from .orchestrator import Orchestrator
from .plugins import default_registry, load_plugins_from_dir
from .scheduling import order_jobs
from .sentinel import Sentinel
from .watcher import ApprovalRegistry, ProcessedRegistry, load_job_file, scan_inbox

# Statuses that terminate processing (won't be retried automatically).
_TERMINAL = {"done", "failed", "blocked"}


def _build(cfg: Config) -> tuple[Orchestrator, IngestClient]:
    ingest = IngestClient(cfg.dashboard_url, cfg.ingest_token)
    executor = make_executor(
        cfg.executor_mode,
        firejail_bin=cfg.firejail_bin,
        allow_unsandboxed=cfg.allow_unsandboxed,
        worker_model=cfg.models.get("worker", "claude-opus-4-8"),
        ingest_url=cfg.dashboard_url,
        ingest_token=cfg.ingest_token,
        hooks_dir=cfg.root / "hooks",
        settings_template=cfg.root / ".claude" / "settings.template.json",
        ollama_url=cfg.ollama_url,
        ollama_model=cfg.ollama_model,
        ollama_models=cfg.ollama_models,
        ollama_roles=cfg.ollama_roles,
        ollama_escalation_model=cfg.ollama_escalation_model,
        ollama_timeout=cfg.ollama_timeout,
        ollama_fallback_model=cfg.ollama_fallback_model,
        offline_fallback=cfg.offline_fallback,
        cache=ResultCache(cfg.cache_dir, enabled=cfg.cache_enabled),
    )
    sentinel = Sentinel(cfg.retry, ingest)
    # Load any custom task plugins from the configured tasks/ directory (§1).
    registry = default_registry()
    load_plugins_from_dir(cfg.plugins_dir, registry)
    orch = Orchestrator(cfg, ingest, executor, Dispatcher(registry=registry), sentinel)
    return orch, ingest


def cmd_submit(cfg: Config, args: argparse.Namespace) -> int:
    src = Path(args.file)
    job = load_job_file(src)  # validates frontmatter
    dest = cfg.inbox / f"{job.id}.md"
    cfg.inbox.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    print(f"submitted {job.id} ({job.type}) -> {dest}")
    return 0


def cmd_new(cfg: Config, args: argparse.Namespace) -> int:
    """Create a valid job in the inbox without hand-writing YAML/UUIDs."""
    job_id = str(uuid.uuid4())
    deadline = (datetime.now(UTC) + timedelta(days=args.days)).replace(microsecond=0)
    lines = [
        "---",
        f"id: {job_id}",
        f"type: {args.type}",
        f"priority: {args.priority}",
        f"deadline: {deadline.isoformat()}",
        f"deliverable_format: {args.deliverable}",
        f"requires_approval: {'true' if args.approve else 'false'}",
    ]
    if args.verify:
        lines.append(f'verify: "{args.verify}"')
    lines += ["---", f"# {args.title}", "", args.description or args.title, ""]
    text = "\n".join(lines)

    cfg.inbox.mkdir(parents=True, exist_ok=True)
    dest = cfg.inbox / f"{job_id}.md"
    dest.write_text(text, encoding="utf-8")
    load_job_file(dest)  # fail loudly if the generated job is somehow invalid
    print(f"created {job_id} ({args.type}) -> {dest}")
    return 0


def cmd_approve(cfg: Config, args: argparse.Namespace) -> int:
    ApprovalRegistry(cfg.state).approve(args.id)
    print(f"approved {args.id}")
    return 0


def cmd_status(cfg: Config, _args: argparse.Namespace) -> int:
    _, ingest = _build(cfg)
    try:
        resp = ingest._client.get(f"{cfg.dashboard_url}/api/tasks")
        resp.raise_for_status()
        tasks = resp.json()["tasks"]
    finally:
        ingest.close()
    if not tasks:
        print("(no tasks)")
        return 0
    for t in tasks:
        print(f"{t['id']:<24} {str(t['status']):<16} {t['type']:<12} ${t['total_cost_usd']:.4f}")
    return 0


def cmd_reset(cfg: Config, _args: argparse.Namespace) -> int:
    for name in ("processed.json", "approved.json"):
        (cfg.state / name).unlink(missing_ok=True)
    for d in (cfg.work, cfg.outbox, cfg.runlog):
        if d.is_dir():
            for child in d.iterdir():
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    print("reset orchestrator state (processed/approved, work/outbox/runlog)")
    return 0


def _process_inbox_once(cfg: Config, orch: Orchestrator) -> list[tuple[str, str]]:
    processed = ProcessedRegistry(cfg.state)
    approvals = ApprovalRegistry(cfg.state)
    results: list[tuple[str, str]] = []
    # Process most-urgent-first by (priority, deadline) so a tight deadline or a
    # priority-1 job is not stuck behind low-priority work (review §2).
    pending = [load_job_file(p) for p in scan_inbox(cfg.inbox)]
    for job in order_jobs(pending):
        if processed.seen(job.id):
            continue
        outcome = orch.process_job(job, approved=approvals.approved(job.id))
        results.append((job.id, outcome.status))
        if outcome.status in _TERMINAL:
            processed.mark(job.id)
    return results


def cmd_run(cfg: Config, args: argparse.Namespace) -> int:
    orch, ingest = _build(cfg)
    try:
        if args.once:
            results = _process_inbox_once(cfg, orch)
            for job_id, status in results:
                print(f"{job_id}: {status}")
            return 0
        print(f"watching {cfg.inbox} (poll {cfg.poll_interval}s, executor={cfg.executor_mode})")
        while True:
            for job_id, status in _process_inbox_once(cfg, orch):
                print(f"{job_id}: {status}")
            time.sleep(cfg.poll_interval)
    finally:
        ingest.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="die-firma", description="Die Firma orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a new job in the inbox (no YAML needed)")
    p_new.add_argument("title", help="short title / first line of the task")
    p_new.add_argument("--type", choices=TASK_TYPES, default="code_gen")
    p_new.add_argument("--priority", type=int, choices=(1, 2, 3), default=2)
    p_new.add_argument(
        "--deliverable", choices=DELIVERABLE_FORMATS, default="file", dest="deliverable"
    )
    p_new.add_argument("--verify", default=None, help="optional reproducible review command")
    p_new.add_argument("--description", default=None, help="longer task description")
    p_new.add_argument("--days", type=int, default=7, help="deadline in N days from now")
    p_new.add_argument("--approve", action="store_true", help="require manual approval")
    p_new.set_defaults(func=cmd_new)

    p_submit = sub.add_parser("submit", help="validate + drop a job into the inbox")
    p_submit.add_argument("file")
    p_submit.set_defaults(func=cmd_submit)

    p_approve = sub.add_parser("approve", help="approve a gated job by id")
    p_approve.add_argument("id")
    p_approve.set_defaults(func=cmd_approve)

    p_status = sub.add_parser("status", help="print task statuses from the dashboard")
    p_status.set_defaults(func=cmd_status)

    p_reset = sub.add_parser("reset", help="clear orchestrator state + work/outbox/runlog")
    p_reset.set_defaults(func=cmd_reset)

    p_run = sub.add_parser("run", help="process the inbox")
    p_run.add_argument("--once", action="store_true", help="process once and exit")
    p_run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    func = args.func
    return int(func(cfg, args))


if __name__ == "__main__":
    sys.exit(main())
