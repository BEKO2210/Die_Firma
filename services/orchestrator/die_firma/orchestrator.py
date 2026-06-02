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

from . import scheduling
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

        # -- plugin validation (task-type-specific acceptance gate) ------
        # The job's task plugin may enforce extra acceptance criteria beyond the
        # verify command (review §1). A failure here fails the job like a review.
        validation = self._dispatcher.validate(job, workdir)
        if not validation.passed:
            self._ingest.emit(
                "status_changed",
                task_id=job.id,
                agent="reviewer",
                status="failed",
                message=f"plugin validation failed: {validation.detail}"[:500],
            )
            log.append(f"failed plugin validation: {validation.detail}")
            return JobOutcome("failed", validation.detail)

        # -- quality gate (real review: critique + refine) ---------------
        # The verify command is a hard pass/fail gate; this is the content
        # review the old pipeline lacked — a reviewer model (and, for web
        # output, a vision model) grades the deliverable and findings are fed
        # back into refine passes. Best-effort: never fails an otherwise-good job.
        self._quality_gate(job, workdir, log)

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
    def _worker_count(self, log: RunLog) -> int:
        """Parallelism for this job: the configured semaphore size, or — when
        [concurrency].adaptive is on — a count sized to the current machine
        (CPU load + free VRAM), bounded by the ceiling (review §2)."""
        baseline = max(1, self._cfg.max_parallel)
        if not getattr(self._cfg, "adaptive_parallel", False):
            return baseline
        cpu_count, load1 = scheduling.cpu_load()
        count = scheduling.adaptive_worker_count(
            baseline,
            cpu_count=cpu_count,
            load1=load1,
            min_workers=int(getattr(self._cfg, "min_parallel", 1)),
            ceiling=int(getattr(self._cfg, "adaptive_ceiling", baseline)),
            vram_free_mb=scheduling.free_vram_mb(),
            vram_per_worker_mb=int(getattr(self._cfg, "vram_per_worker_mb", 0)),
        )
        if count != baseline:
            log.append(f"adaptive parallelism: {count} workers (cpu={cpu_count} load1={load1:.2f})")
        return count

    def _run_subtasks(
        self, job: Job, plan: Plan, workdir: Path, log: RunLog
    ) -> dict[str, ExecResult]:
        by_id = {s.id: s for s in plan.subtasks}
        done: set[str] = set()
        results: dict[str, ExecResult] = {}
        workers = self._worker_count(log)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while len(done) < len(by_id):
                ready = [
                    s
                    for s in plan.subtasks
                    if s.id not in done and all(d in done for d in s.depends_on)
                ]
                # Bound parallelism to the (possibly adaptive) worker count.
                batch = ready[:workers]
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
            emitted = {"out": 0}

            def progress(_din: int, dout: int) -> None:
                # Live token throughput while the model streams its answer, so the
                # dashboard's tokens/sec + agent activity update during generation
                # instead of only when the (minutes-long) call returns.
                emitted["out"] += dout
                self._ingest.emit(
                    "token_usage",
                    task_id=job.id,
                    subtask_id=subtask.id,
                    agent="worker",
                    tokens_out=dout,
                )

            res = self._executor.run(job, subtask, workdir, attempt=_n, progress=progress)
            # Emit only the REMAINDER at the end so streamed deltas aren't double-counted.
            self._ingest.emit(
                "tool_call_end",
                task_id=job.id,
                subtask_id=subtask.id,
                agent="worker",
                tokens_in=res.tokens_in,
                tokens_out=max(0, res.tokens_out - emitted["out"]),
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

    # -- quality gate (real content review + refine) --------------------
    def _quality_gate(self, job: Job, workdir: Path, log: RunLog) -> None:
        """Critique the deliverable with a reviewer model (and a vision model
        for web pages), feeding findings back into refine passes. Attributes
        token usage to the `reviewer` agent so the monitor finally reflects it.
        Entirely best-effort: any error is logged and swallowed."""
        cfg = self._cfg
        if not getattr(cfg, "quality_enabled", False):
            return
        if getattr(self._executor, "mode", "") != "ollama":
            return

        from . import quality as Q
        from .design import design_system_prompt, is_frontend
        from .ollama_client import OllamaClient
        from .router import Router

        files = Q.produced_files(workdir)
        if not files:
            return

        client = OllamaClient(getattr(cfg, "ollama_url", "http://localhost:11434"))
        router = Router(
            per_type=dict(getattr(cfg, "ollama_models", {}) or {}),
            roles=dict(getattr(cfg, "ollama_roles", {}) or {}),
            default_model=getattr(cfg, "ollama_model", "qwen2.5-coder:14b"),
            escalation_model=getattr(cfg, "ollama_escalation_model", "deepseek-r1:14b"),
        )
        review_model = router.review_model()
        code_model = router.per_type.get(job.type, router.default_model)
        min_score = int(getattr(cfg, "quality_min_score", 75))
        max_passes = int(getattr(cfg, "quality_max_refine_passes", 2))
        web = is_frontend(job, files)
        vision_model = router.vision_model()
        visual_ok = (
            web and bool(getattr(cfg, "quality_visual", True)) and client.has_model(vision_model)
        )

        self._ingest.emit("status_changed", task_id=job.id, agent="reviewer", status="review")
        try:
            for p in range(max_passes + 1):
                crit = Q.critique_text(client, review_model, job, files)
                self._ingest.emit(
                    "token_usage",
                    task_id=job.id,
                    agent="reviewer",
                    tokens_in=crit.tokens_in,
                    tokens_out=crit.tokens_out,
                )
                self._ingest.emit(
                    "log",
                    task_id=job.id,
                    agent="reviewer",
                    message=f"review score={crit.score} — {crit.summary}"[:500],
                )
                log.append(f"critique score={crit.score} pass={crit.passed}: {crit.summary}")
                findings = list(crit.actionable("medium"))
                passed = crit.passed and crit.score >= min_score

                if visual_ok:
                    entry = Q.html_entrypoint(workdir)
                    png = workdir / ".preview.png"
                    if entry is not None and Q.render_screenshot(entry, png):
                        vcrit = Q.critique_visual(client, vision_model, job, png)
                        self._ingest.emit(
                            "token_usage",
                            task_id=job.id,
                            agent="reviewer",
                            tokens_in=vcrit.tokens_in,
                            tokens_out=vcrit.tokens_out,
                        )
                        self._ingest.emit(
                            "log",
                            task_id=job.id,
                            agent="reviewer",
                            message=f"visual score={vcrit.score} — {vcrit.summary}"[:500],
                        )
                        log.append(f"visual score={vcrit.score}: {vcrit.summary}")
                        findings += list(vcrit.actionable("medium"))
                        passed = passed and vcrit.passed and vcrit.score >= min_score
                        png.unlink(missing_ok=True)

                if passed or not findings or p >= max_passes:
                    log.append(f"quality gate done after {p} refine pass(es)")
                    break

                brief = design_system_prompt() if web else ""
                new_files, tin, tout = Q.refine(
                    client, code_model, job, files, findings, extra_brief=brief
                )
                for rel, content in new_files.items():
                    dest = workdir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(content, encoding="utf-8")
                self._ingest.emit(
                    "token_usage",
                    task_id=job.id,
                    agent="worker",
                    tokens_in=tin,
                    tokens_out=tout,
                )
                self._ingest.emit(
                    "log",
                    task_id=job.id,
                    agent="reviewer",
                    message=f"refine pass {p + 1}: fixed {len(findings)} issue(s)",
                )
                log.append(f"refine pass {p + 1}: {len(findings)} issues")
                files = Q.produced_files(workdir)
        except Exception as exc:  # noqa: BLE001 — quality gate must never crash a job
            log.append(f"quality gate error (skipped): {exc}")
        finally:
            client.close()
