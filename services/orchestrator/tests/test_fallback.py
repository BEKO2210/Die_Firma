from conftest import make_job

from die_firma.fallback import heuristic_artifact
from die_firma.models import Subtask


def test_heuristic_artifact_marks_placeholder_and_picks_filename():
    job = make_job(body="# Build a login page\nDetails here.")
    st = Subtask(id="j:implement", title="Implement", action="implement")
    files = heuristic_artifact(job, st, reason="ConnectError")
    assert set(files) == {"implement.md"}
    body = files["implement.md"]
    assert "Platzhalter" in body
    assert "ConnectError" in body
    assert "Build a login page" in body


def test_heuristic_artifact_unknown_action_falls_back_to_action_name():
    job = make_job()
    files = heuristic_artifact(job, Subtask(id="s", title="t", action="weird"))
    assert "weird.md" in files
