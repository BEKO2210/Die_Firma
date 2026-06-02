"""Orchestrator: the autonomous state machine tying everything together.

Flow per job: cost guard → approval gate → task_created → dispatch (DAG) →
bounded-parallel sub-task execution (sentinel-guarded) → review → delivery →
done. All state transitions are emitted as telemetry to /api/ingest; the
filesystem (inbox/outbox/work) remains the source of truth.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .cost import evaluate
from .dag import validate_dag
from .delivery import deliver
from .dispatcher import Dispatcher
from .executor import ExecResult, Executor
from .ingest_client import IngestClient
from .models import Job, Plan, Subtask
from .retry import RetryExhausted
from .reviewer import review
from .runlog import RunLog
from .sentinel import Sentinel


class ConfigLike(Protocol):
    """Structural typing for the bits of Config the orchestrator uses.

    Members are read-only properties so the frozen Config dataclass (and test
    stubs) satisfy the protocol.
    """

    @property
    def work(self) -> Path: ...
    @property
    def outbox(self) -> Path: ...
    @property
    def runlog(self) -> Path: ...
    @property
    def daily_usd_limit(self) -> float: ...
    @property
    def max_parallel(self) -> int: ...


class WorkerFailure(RuntimeError):
    """A sub-task execution reported failure (drives a retry)."""


@dataclass
class JobOutcome:
    status: str
    detail: str = ""


def _snippet(text: str, limit: int = 200) -> str:
    """One-line, whitespace-collapsed preview of a deliverable."""
    collapsed = " ".join(text.split())
    return collapsed[:limit]


def _describe(subtask: Subtask, res: ExecResult) -> str:
    """Human-readable 'what this step did', for the live telemetry terminal."""
    model = res.model or "mock"
    body = _snippet(res.output, 160)
    return f"{subtask.action} via {model}: {body}"[:500]


def _build_summary(job: Job, title: str, plan: Plan, results: dict[str, ExecResult]) -> str:
    """A SUMMARY.md that states exactly what was done, per step, with the model."""
    models_used = sorted({r.model for r in results.values() if r.model})
    model_line = ", ".join(models_used) if models_used else "mock"
    lines = [
        f"# {title}",
        "",
        f"- **Task-ID:** {job.id}",
        f"- **Typ:** {job.type}",
        f"- **Lieferform:** {job.deliverable_format}",
        "- **Status:** done",
        f"- **Modell(e):** {model_line}",
        "",
        "## Schritte — was wurde gemacht",
        "",
    ]
    for st in plan.subtasks:
        res = results.get(st.id)
        model = res.model if res and res.model else "mock"
        files = sorted(res.artifacts) if res else []
        lines.append(f"### {st.action} — {st.title}")
        lines.append(f"_Modell: {model}_")
        if files:
            lines.append("Dateien: " + ", ".join(f"`{f}`" for f in files))
        preview = _snippet(res.output, 240) if res else ""
        if preview:
            lines += ["", f"> {preview}…"]
        lines.append("")
    all_files = sorted({f for r in results.values() for f in r.artifacts})
    lines.append("## Artefakte")
    lines += [f"- `{f}`" for f in all_files] or ["- (keine)"]
    return "\n".join(lines) + "\n"


class Orchestrator:
    def __init__(
        self,
        config: ConfigLike,
        ingest: IngestClient,
        executor: Executor,
        dispatcher: Dispatcher,
        sentinel: Sentinel,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cfg = config
        self._ingest = ingest
        self._executor = executor
        self._dispatcher = dispatcher
        self._sentinel = sentinel
        self._sleep = sleep

    # -- gates -----------------------------------------------------------
    def cost_allows_dispatch(self) -> bool:
        spent = self._ingest.today_spend_usd()
        return evaluate(spent, self._cfg.daily_usd_limit).allowed

    # -- main entry ------------------------------------------------------
    def process_job(self, job: Job, *, approved: bool = False) -> JobOutcome:
        log = RunLog(self._cfg.runlog, job.id)
        log.append(f"received job type={job.type} priority={job.priority}")

        if not self.cost_allows_dispatch():
            self._ingest.emit(
                "log",
                task_id=job.id,
                agent="dispatcher",
                message="daily cost limit reached; queue paused",
                status="queued",
            )
            log.append("queue paused: daily cost limit reached")
            return JobOutcome("queued", "cost limit reached")

        task_data = {
            "type": job.type,
            "priority": job.priority,
            "deadline": job.deadline.isoformat(),
            "title": job.body.splitlines()[0].lstrip("# ").strip() if job.body else job.id,
            "deliverable_format": job.deliverable_format,
        }

        if job.gated and not approved:
            self._ingest.emit(
                "task_created",
                task_id=job.id,
                agent="dispatcher",
                status="awaiting_approval",
                data=task_data,
            )
            log.append("awaiting approval (gated)")
            return JobOutcome("awaiting_approval")

        self._ingest.emit(
            "task_created",
            task_id=job.id,
            agent="dispatcher",
            status="queued",
            data=task_data,
        )

        # -- dispatch ----------------------------------------------------
        self._ingest.emit("agent_assigned", task_id=job.id, agent="dispatcher", status="planning")
        plan = self._dispatcher.plan(job)
        validate_dag(plan.graph())
        for st in plan.subtasks:
            self._ingest.emit(
                "subtask_created",
                task_id=job.id,
                subtask_id=st.id,
                agent="dispatcher",
                status="queued",
                data={"title": st.title, "depends_on": st.depends_on},
            )
        log.append(f"planned {len(plan.subtasks)} sub-tasks")

        # -- execute -----------------------------------------------------
        self._ingest.emit("status_changed", task_id=job.id, agent="worker", status="running")
        workdir = self._cfg.work / job.id
        try:
            results = self._run_subtasks(job, plan, workdir, log)
        except RetryExhausted:
            # Sentinel already emitted blocked + escalation.
            log.append("blocked: sub-task retries exhausted")
            return JobOutcome("blocked", "retries exhausted")

        # -- review ------------------------------------------------------
        self._ingest.emit("status_changed", task_id=job.id, agent="reviewer", status="review")
        result = review(job.verify, workdir)
        self._ingest.emit(
            "log",
            task_id=job.id,
            agent="reviewer",
            message=f"review {'passed' if result.passed else 'failed'}: {result.detail}"[:500],
        )
        if not result.passed:
            self._ingest.emit(
                "status_changed",
                task_id=job.id,
                agent="reviewer",
                status="failed",
                message="verify command failed",
            )
            log.append(f"failed review: {result.detail}")
            return JobOutcome("failed", result.detail)

        # -- deliver -----------------------------------------------------
        summary = _build_summary(job, str(task_data["title"]), plan, results)
        delivery = deliver(
            job_id=job.id,
            deliverable_format=job.deliverable_format,
            workdir=workdir,
            outbox_root=self._cfg.outbox,
            summary=summary,
        )
        self._ingest.emit(
            "status_changed",
            task_id=job.id,
            agent="worker",
            status="done",
            message=f"delivered to {delivery.outbox_dir.name}"
            + (f" (branch {delivery.branch})" if delivery.branch else ""),
        )
        log.append(f"done: outbox={delivery.outbox_dir} branch={delivery.branch}")
        return JobOutcome("done")

    # -- sub-task scheduling --------------------------------------------
    def _run_subtasks(
        self, job: Job, plan: Plan, workdir: Path, log: RunLog
    ) -> dict[str, ExecResult]:
        by_id = {s.id: s for s in plan.subtasks}
        done: set[str] = set()
        results: dict[str, ExecResult] = {}
        with ThreadPoolExecutor(max_workers=max(1, self._cfg.max_parallel)) as pool:
            while len(done) < len(by_id):
                ready = [
                    s
                    for s in plan.subtasks
                    if s.id not in done and all(d in done for d in s.depends_on)
                ]
                # Bound parallelism to the configured semaphore size.
                batch = ready[: max(1, self._cfg.max_parallel)]
                futures = {pool.submit(self._run_one, job, s, workdir): s for s in batch}
                for fut, st in futures.items():
                    results[st.id] = fut.result()  # raises RetryExhausted on terminal failure
                    done.add(st.id)
                    log.append(f"sub-task {st.id} done")
        return results

    def _run_one(self, job: Job, subtask: Subtask, workdir: Path) -> ExecResult:
        self._ingest.emit(
            "subtask_updated",
            task_id=job.id,
            subtask_id=subtask.id,
            agent="worker",
            status="running",
        )
        holder: dict[str, ExecResult] = {}

        def attempt(_n: int) -> None:
            self._ingest.emit(
                "tool_call_start",
                task_id=job.id,
                subtask_id=subtask.id,
                agent="worker",
                message=subtask.action,
            )
            res = self._executor.run(job, subtask, workdir)
            self._ingest.emit(
                "tool_call_end",
                task_id=job.id,
                subtask_id=subtask.id,
                agent="worker",
                tokens_in=res.tokens_in,
                tokens_out=res.tokens_out,
                cost_usd=res.cost_usd,
            )
            if not res.ok:
                raise WorkerFailure(res.output)
            holder["res"] = res

        self._sentinel.guard(attempt, task_id=job.id, subtask_id=subtask.id)
        res = holder["res"]
        # Concrete telemetry: what this step actually did + which model produced it.
        self._ingest.emit(
            "log",
            task_id=job.id,
            subtask_id=subtask.id,
            agent="worker",
            message=_describe(subtask, res),
        )
        self._ingest.emit(
            "subtask_updated",
            task_id=job.id,
            subtask_id=subtask.id,
            agent="worker",
            status="done",
        )
        return res
