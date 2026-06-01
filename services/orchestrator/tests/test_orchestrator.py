from pathlib import Path

from conftest import FakeIngest, make_job

from die_firma.dispatcher import Dispatcher
from die_firma.executor import ExecResult, MockExecutor
from die_firma.models import Job, Subtask
from die_firma.orchestrator import Orchestrator
from die_firma.retry import RetryPolicy
from die_firma.sentinel import Sentinel


def _make(stub_config, ingest, executor, *, notes=None):
    sentinel = Sentinel(
        RetryPolicy(2, (0.0,)),
        ingest,  # type: ignore[arg-type]
        sleep=lambda _s: None,
        notifier=lambda t, b: (notes.append((t, b)) if notes is not None else None) or True,
    )
    return Orchestrator(
        stub_config, ingest, executor, Dispatcher(), sentinel, sleep=lambda _s: None
    )


class FailingExecutor:
    mode = "mock"

    def run(self, job: Job, subtask: Subtask, workdir: Path) -> ExecResult:
        workdir.mkdir(parents=True, exist_ok=True)
        return ExecResult(ok=False, output="boom")


def test_happy_path_done(stub_config):
    ingest = FakeIngest()
    orch = _make(stub_config, ingest, MockExecutor())
    outcome = orch.process_job(make_job(type="code_gen", deliverable_format="file"))
    assert outcome.status == "done"
    assert "task_created" in ingest.kinds()
    assert ingest.kinds().count("subtask_created") == 2
    assert "done" in ingest.statuses()
    # deliverable landed in outbox
    out = stub_config.outbox / "11111111-1111-1111-1111-111111111111"
    assert (out / "SUMMARY.md").is_file()
    assert any(p.suffix == ".txt" for p in out.iterdir())
    # runlog written
    assert (stub_config.runlog / "11111111-1111-1111-1111-111111111111.log").is_file()


def test_cost_limit_pauses(stub_config):
    ingest = FakeIngest(spend=999.0)
    orch = _make(stub_config, ingest, MockExecutor())
    outcome = orch.process_job(make_job())
    assert outcome.status == "queued"
    assert "queued" in ingest.statuses()
    assert "task_created" not in ingest.kinds()


def test_approval_gate(stub_config):
    ingest = FakeIngest()
    orch = _make(stub_config, ingest, MockExecutor())
    gated = make_job(priority=1)
    assert orch.process_job(gated, approved=False).status == "awaiting_approval"
    assert "awaiting_approval" in ingest.statuses()
    # once approved it runs to completion
    ingest2 = FakeIngest()
    orch2 = _make(stub_config, ingest2, MockExecutor())
    assert orch2.process_job(gated, approved=True).status == "done"


def test_review_failure(stub_config):
    ingest = FakeIngest()
    orch = _make(stub_config, ingest, MockExecutor())
    outcome = orch.process_job(make_job(verify="false"))
    assert outcome.status == "failed"
    assert "failed" in ingest.statuses()


def test_blocked_after_retries_escalates(stub_config):
    ingest = FakeIngest()
    notes: list[tuple[str, str]] = []
    orch = _make(stub_config, ingest, FailingExecutor(), notes=notes)
    outcome = orch.process_job(make_job())
    assert outcome.status == "blocked"
    assert "escalation" in ingest.kinds()
    assert "blocked" in ingest.statuses()
    assert notes  # desktop notification attempted


def test_git_branch_delivery(stub_config):
    ingest = FakeIngest()
    orch = _make(stub_config, ingest, MockExecutor())
    outcome = orch.process_job(make_job(deliverable_format="git_branch"))
    assert outcome.status == "done"
    workdir = stub_config.work / "11111111-1111-1111-1111-111111111111"
    assert (workdir / ".git").exists()
