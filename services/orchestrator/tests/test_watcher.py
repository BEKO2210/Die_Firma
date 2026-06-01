import pytest

from die_firma.watcher import (
    ApprovalRegistry,
    ProcessedRegistry,
    load_job_file,
    parse_frontmatter,
    parse_job,
    scan_inbox,
)

DOC = """---
id: abc-123
type: code_gen
priority: 2
deadline: 2026-06-05T18:00:00+02:00
deliverable_format: git_branch
requires_approval: false
allowed_paths:
  - /home/x/proj
verify: "true"
---
# Title line
Body text.
"""


def test_parse_frontmatter_ok():
    meta, body = parse_frontmatter(DOC)
    assert meta["id"] == "abc-123"
    assert body.startswith("# Title line")


def test_parse_frontmatter_errors():
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_frontmatter("no frontmatter here")
    with pytest.raises(ValueError, match="unterminated"):
        parse_frontmatter("---\nid: x\n")
    with pytest.raises(ValueError, match="mapping"):
        parse_frontmatter("---\n- just\n- a\n- list\n---\nbody")


def test_parse_job_builds_model():
    job = parse_job(DOC)
    assert job.type == "code_gen"
    assert job.allowed_paths == ["/home/x/proj"]
    assert job.verify == "true"
    assert job.body.startswith("# Title line")


def test_load_job_file_and_scan(tmp_path):
    (tmp_path / "b.md").write_text(DOC.replace("abc-123", "b"), encoding="utf-8")
    (tmp_path / "a.md").write_text(DOC.replace("abc-123", "a"), encoding="utf-8")
    (tmp_path / "note.txt").write_text("ignore", encoding="utf-8")
    files = scan_inbox(tmp_path)
    assert [p.name for p in files] == ["a.md", "b.md"]
    assert load_job_file(files[0]).id == "a"
    assert scan_inbox(tmp_path / "nope") == []


def test_processed_registry_persists_and_tolerates_corruption(tmp_path):
    reg = ProcessedRegistry(tmp_path)
    assert not reg.seen("x")
    reg.mark("x")
    assert ProcessedRegistry(tmp_path).seen("x")  # reloaded from disk
    (tmp_path / "processed.json").write_text("{bad json", encoding="utf-8")
    assert not ProcessedRegistry(tmp_path).seen("x")  # corrupt -> empty


def test_approval_registry(tmp_path):
    reg = ApprovalRegistry(tmp_path)
    assert not reg.approved("j")
    reg.approve("j")
    assert ApprovalRegistry(tmp_path).approved("j")
    (tmp_path / "approved.json").write_text("nope", encoding="utf-8")
    assert not ApprovalRegistry(tmp_path).approved("j")
