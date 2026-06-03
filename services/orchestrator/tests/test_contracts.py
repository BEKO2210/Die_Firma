"""Drift guard: the Python data contract must match the canonical
contracts/task-types.json (review 'Next' — single source of truth). If someone
adds a task type / status / format on one side only, this fails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from die_firma import models

CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "task-types.json").read_text(
        encoding="utf-8"
    )
)


def test_task_types_match_contract():
    assert list(models.TASK_TYPES) == CONTRACT["task_types"]
    assert sorted(get_args(models.TaskType)) == sorted(CONTRACT["task_types"])


def test_deliverable_formats_match_contract():
    assert list(models.DELIVERABLE_FORMATS) == CONTRACT["deliverable_formats"]
    assert sorted(get_args(models.DeliverableFormat)) == sorted(CONTRACT["deliverable_formats"])


def test_agents_match_contract():
    assert sorted(get_args(models.Agent)) == sorted(CONTRACT["agents"])


def test_statuses_match_contract():
    assert sorted(get_args(models.Status)) == sorted(CONTRACT["statuses"])


def test_event_kinds_match_contract():
    assert frozenset(CONTRACT["event_kinds"]) == models.EVENT_KINDS
