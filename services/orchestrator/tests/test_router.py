"""Router: role detection, per-type/per-role resolution, retry escalation."""

from __future__ import annotations

from datetime import UTC, datetime

from die_firma.models import Job, Subtask
from die_firma.router import CODE, GENERAL, REVIEW, Router


def _job(t: str = "code_gen") -> Job:
    return Job(
        id="j1",
        type=t,  # type: ignore[arg-type]
        priority=2,
        deadline=datetime(2030, 1, 1, tzinfo=UTC),
        deliverable_format="file",
        body="build a webseite",
    )


def _st(action: str) -> Subtask:
    return Subtask(id=f"j1:{action}", title=action, action=action)


def test_role_for_known_and_unknown_actions():
    r = Router()
    assert r.role_for(_job(), _st("implement")) == CODE
    assert r.role_for(_job(), _st("self_review")) == REVIEW
    assert r.role_for(_job(), _st("ingest")) == GENERAL
    # Unknown action: code-ish job -> CODE, else GENERAL.
    assert r.role_for(_job("code_gen"), _st("mystery")) == CODE
    assert r.role_for(_job("data_prep"), _st("mystery")) == GENERAL


def test_per_type_wins_for_code_role():
    r = Router(per_type={"code_gen": "qwen2.5-coder:7b"}, default_model="x")
    assert r.model_for(_job("code_gen"), _st("implement")) == "qwen2.5-coder:7b"


def test_role_override_and_defaults():
    r = Router(roles={"review": "phi4:14b"})
    assert r.model_for(_job(), _st("self_review")) == "phi4:14b"
    # Vision/review/general helpers expose their resolved models.
    assert r.review_model() == "phi4:14b"
    assert r.vision_model() == "llava:7b"


def test_general_role_falls_back_to_data_prep_then_default():
    r = Router(per_type={"data_prep": "qwen2.5:14b"})
    assert r.model_for(_job("data_prep"), _st("ingest")) == "qwen2.5:14b"
    # No data_prep entry -> baked-in general default.
    assert Router().model_for(_job("data_prep"), _st("ingest")) == "qwen2.5:14b"


def test_escalation_on_retry():
    r = Router(escalation_model="deepseek-r1:14b")
    # First attempt = normal routing; second = escalation model regardless of role.
    assert r.model_for(_job(), _st("implement"), attempt=1) == "qwen2.5-coder:14b"
    assert r.model_for(_job(), _st("implement"), attempt=2) == "deepseek-r1:14b"
    assert r.model_for(_job(), _st("self_review"), attempt=3) == "deepseek-r1:14b"


def test_escalation_respects_reason_role_override():
    r = Router(roles={"reason": "phi4:14b"}, escalation_model="deepseek-r1:14b")
    assert r.model_for(_job(), _st("implement"), attempt=2) == "phi4:14b"
