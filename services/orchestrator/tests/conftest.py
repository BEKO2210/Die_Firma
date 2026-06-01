from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from die_firma.models import Job


def make_job(**overrides: Any) -> Job:
    base: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "code_gen",
        "priority": 2,
        "deadline": datetime(2026, 6, 5, 18, 0, tzinfo=UTC),
        "deliverable_format": "file",
        "body": "# Build a thing\nDo the work.",
    }
    base.update(overrides)
    return Job(**base)


@dataclass
class FakeIngest:
    """Records emits; returns a configurable daily spend for the cost guard."""

    spend: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, kind: str, **kwargs: Any) -> int:
        self.events.append({"kind": kind, **kwargs})
        return len(self.events)

    def today_spend_usd(self) -> float:
        return self.spend

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.events]

    def statuses(self) -> list[str]:
        return [e["status"] for e in self.events if e.get("status")]


@dataclass
class StubConfig:
    work: Path
    outbox: Path
    runlog: Path
    daily_usd_limit: float = 10.0
    max_parallel: int = 2


@pytest.fixture
def stub_config(tmp_path: Path) -> StubConfig:
    return StubConfig(
        work=tmp_path / "work",
        outbox=tmp_path / "outbox",
        runlog=tmp_path / "runlog",
    )
