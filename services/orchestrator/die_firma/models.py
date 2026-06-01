"""Pydantic models — kept in lockstep with the dashboard data contract
(apps/dashboard/src/lib/types.ts) and BUILD_PROMPT §4."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TaskType = Literal["code_gen", "code_review", "automation", "data_prep"]
DeliverableFormat = Literal["git_branch", "file", "report"]
Agent = Literal["dispatcher", "worker", "reviewer", "sentinel"]
Status = Literal[
    "queued",
    "planning",
    "running",
    "review",
    "blocked",
    "done",
    "failed",
    "cancelled",
    "awaiting_approval",
]

EVENT_KINDS = frozenset(
    {
        "task_created",
        "task_updated",
        "subtask_created",
        "subtask_updated",
        "agent_assigned",
        "tool_call_start",
        "tool_call_end",
        "status_changed",
        "log",
        "token_usage",
        "cost_updated",
        "error",
        "escalation",
    }
)


class Job(BaseModel):
    """A job parsed from an inbox/<id>.md frontmatter + markdown body."""

    model_config = {"extra": "forbid"}

    id: str
    type: TaskType
    priority: int = Field(ge=1, le=3)
    deadline: datetime
    deliverable_format: DeliverableFormat
    requires_approval: bool = False
    allowed_paths: list[str] = Field(default_factory=list)
    verify: str | None = None
    # Populated from the markdown body, not the frontmatter:
    body: str = ""
    source_path: Path | None = None

    @field_validator("id")
    @classmethod
    def _id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("id must not be empty")
        return v.strip()

    @property
    def gated(self) -> bool:
        """Whether this job needs manual approval before merge/dispatch."""
        return self.requires_approval or self.priority == 1


class Subtask(BaseModel):
    """An atomic unit of work produced by the dispatcher."""

    model_config = {"extra": "forbid"}

    id: str
    title: str
    action: str
    depends_on: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    """A dispatcher's decomposition of a job into a shallow DAG."""

    model_config = {"extra": "forbid"}

    subtasks: list[Subtask]

    def graph(self) -> dict[str, list[str]]:
        return {s.id: list(s.depends_on) for s in self.subtasks}
