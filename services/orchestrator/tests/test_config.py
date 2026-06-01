import pytest

from die_firma.config import find_repo_root, load_config, load_dotenv
from die_firma.secrets import SecretError

CONFIG_TOML = """
[general]
inbox_dir = "inbox"
outbox_dir = "outbox"
work_dir = "work"
runlog_dir = "runlog"
state_dir = "state"
poll_interval_seconds = 2.0
[dashboard]
url = "http://127.0.0.1:4321"
[executor]
mode = "mock"
firejail_bin = "firejail"
allow_unsandboxed = false
[concurrency]
max_parallel_tasks = 2
[retry]
max_attempts = 3
backoff_seconds = [2, 4, 8]
[cost]
daily_usd_limit = 10.0
[models]
worker = "claude-opus-4-8"
[approval]
gate_priority = 1
"""

GOOD_TOKEN = "Xk7_3sdf92kfjs03ksdf-aiwe9382"


def _write_repo(tmp_path):
    (tmp_path / "config.toml").write_text(CONFIG_TOML, encoding="utf-8")
    return tmp_path


def test_find_repo_root(tmp_path):
    repo = _write_repo(tmp_path)
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == repo
    with pytest.raises(FileNotFoundError):
        find_repo_root(tmp_path.parent / "definitely-not-a-repo-root-xyz")


def test_load_dotenv_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO_X", raising=False)
    monkeypatch.setenv("BAR_X", "already")
    (tmp_path / ".env").write_text(
        'FOO_X="hello"\nBAR_X=should-not-win\n# c\nbad line\n', encoding="utf-8"
    )
    load_dotenv(tmp_path / ".env")
    import os

    assert os.environ["FOO_X"] == "hello"
    assert os.environ["BAR_X"] == "already"
    load_dotenv(tmp_path / "missing.env")  # no-op


def test_load_config_ok_and_secret_check(tmp_path, monkeypatch):
    repo = _write_repo(tmp_path)
    monkeypatch.setenv("DIE_FIRMA_INGEST_TOKEN", GOOD_TOKEN)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = load_config(start=repo)
    assert cfg.executor_mode == "mock"
    assert cfg.max_parallel == 2
    assert cfg.retry.backoff_seconds == (2.0, 4.0, 8.0)
    assert cfg.inbox == (repo / "inbox").resolve()
    # anthropic key only validated lazily
    with pytest.raises(SecretError):
        cfg.get_anthropic_key()


def test_load_config_rejects_placeholder_token(tmp_path, monkeypatch):
    repo = _write_repo(tmp_path)
    monkeypatch.setenv("DIE_FIRMA_INGEST_TOKEN", "changeme")
    with pytest.raises(SecretError):
        load_config(start=repo)
