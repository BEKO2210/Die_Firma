from pathlib import Path
from types import SimpleNamespace

from conftest import make_job

from die_firma import cli
from die_firma.config import Config
from die_firma.orchestrator import JobOutcome
from die_firma.retry import RetryPolicy
from die_firma.watcher import ApprovalRegistry, ProcessedRegistry

DOC = """---
id: cli-job-1
type: code_gen
priority: 2
deadline: 2026-06-05T18:00:00+02:00
deliverable_format: file
---
# Title
Body.
"""


def make_cfg(tmp_path: Path) -> Config:
    for name in ("inbox", "outbox", "work", "runlog", "state"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        inbox=tmp_path / "inbox",
        outbox=tmp_path / "outbox",
        work=tmp_path / "work",
        runlog=tmp_path / "runlog",
        state=tmp_path / "state",
        poll_interval=2.0,
        dashboard_url="http://127.0.0.1:4321",
        executor_mode="mock",
        firejail_bin="firejail",
        allow_unsandboxed=False,
        ollama_url="http://localhost:11434",
        ollama_model="llama3.2",
        ollama_models={},
        max_parallel=2,
        retry=RetryPolicy(3, (2.0, 4.0, 8.0)),
        daily_usd_limit=10.0,
        models={"worker": "claude-opus-4-8"},
        gate_priority=1,
        ingest_token="Xk7_3sdf92kfjs03ksdf-aiwe9382",
    )


def test_build_parser_has_all_commands():
    parser = cli.build_parser()
    args = parser.parse_args(["run", "--once"])
    assert args.command == "run" and args.once is True
    assert parser.parse_args(["approve", "abc"]).id == "abc"


def test_cmd_submit_copies_into_inbox(tmp_path):
    cfg = make_cfg(tmp_path)
    src = tmp_path / "drop.md"
    src.write_text(DOC, encoding="utf-8")
    rc = cli.cmd_submit(cfg, SimpleNamespace(file=str(src)))
    assert rc == 0
    assert (cfg.inbox / "cli-job-1.md").is_file()


def test_cmd_new_creates_valid_job(tmp_path):
    cfg = make_cfg(tmp_path)
    args = SimpleNamespace(
        title="Build a greeting module",
        type="code_gen",
        priority=2,
        deliverable="file",
        verify="ls *.txt",
        description="Generate a small module.",
        days=7,
        approve=False,
    )
    assert cli.cmd_new(cfg, args) == 0
    files = list(cfg.inbox.glob("*.md"))
    assert len(files) == 1
    # The generated file must parse back into a valid Job (validated in cmd_new).
    from die_firma.watcher import load_job_file

    job = load_job_file(files[0])
    assert job.type == "code_gen"
    assert job.verify == "ls *.txt"
    assert job.body.startswith("# Build a greeting module")


def test_cmd_new_gated(tmp_path):
    cfg = make_cfg(tmp_path)
    args = SimpleNamespace(
        title="Rotate secrets",
        type="code_gen",
        priority=1,
        deliverable="report",
        verify=None,
        description=None,
        days=3,
        approve=True,
    )
    assert cli.cmd_new(cfg, args) == 0
    from die_firma.watcher import load_job_file

    job = load_job_file(next(cfg.inbox.glob("*.md")))
    assert job.requires_approval is True and job.gated is True


def test_cmd_approve(tmp_path):
    cfg = make_cfg(tmp_path)
    assert cli.cmd_approve(cfg, SimpleNamespace(id="j9")) == 0
    assert ApprovalRegistry(cfg.state).approved("j9")


def test_cmd_reset_clears_state(tmp_path):
    cfg = make_cfg(tmp_path)
    (cfg.work / "junk").mkdir()
    (cfg.outbox / "f.txt").write_text("x", encoding="utf-8")
    (cfg.runlog / ".gitkeep").write_text("", encoding="utf-8")
    ProcessedRegistry(cfg.state).mark("old")
    assert cli.cmd_reset(cfg, SimpleNamespace()) == 0
    assert not (cfg.work / "junk").exists()
    assert not (cfg.outbox / "f.txt").exists()
    assert (cfg.runlog / ".gitkeep").exists()  # preserved
    assert not ProcessedRegistry(cfg.state).seen("old")


def test_process_inbox_once_marks_terminal(tmp_path):
    cfg = make_cfg(tmp_path)
    (cfg.inbox / "cli-job-1.md").write_text(DOC, encoding="utf-8")

    class FakeOrch:
        def __init__(self) -> None:
            self.calls = 0

        def process_job(self, job, *, approved=False):  # noqa: ANN001
            self.calls += 1
            return JobOutcome("done")

    orch = FakeOrch()
    results = cli._process_inbox_once(cfg, orch)  # type: ignore[arg-type]
    assert results == [("cli-job-1", "done")]
    # Second pass is idempotent: already processed -> skipped.
    assert cli._process_inbox_once(cfg, orch) == []
    assert orch.calls == 1


def test_process_inbox_once_keeps_unfinished(tmp_path):
    cfg = make_cfg(tmp_path)
    (cfg.inbox / "cli-job-1.md").write_text(DOC, encoding="utf-8")

    class WaitingOrch:
        def process_job(self, job, *, approved=False):  # noqa: ANN001
            return JobOutcome("awaiting_approval")

    cli._process_inbox_once(cfg, WaitingOrch())  # type: ignore[arg-type]
    # Not terminal -> still re-processable next pass.
    assert not ProcessedRegistry(cfg.state).seen("cli-job-1")
    _ = make_job  # silence unused import in case
