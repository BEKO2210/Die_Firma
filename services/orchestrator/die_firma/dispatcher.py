"""Dispatcher: decompose a job into a shallow DAG of atomic sub-tasks.

Deterministic rule-based decomposition is the default and the guaranteed
fallback if the LLM dispatcher fails (prompt §1: "deterministic rule fallback,
if the dispatcher fails"). Every plan is validated to be a DAG ≤2 levels deep.
"""

from __future__ import annotations

from .dag import validate_dag
from .models import Job, Plan, Subtask

# One small, fixed decomposition per job type. Each stays within 2 levels.
_RULES: dict[str, list[tuple[str, str, list[str]]]] = {
    "code_gen": [
        ("implement", "Implement the requested change", []),
        ("self_review", "Self-review and prepare the deliverable", ["implement"]),
    ],
    "code_review": [
        ("analyze", "Analyze the target and produce a review report", []),
    ],
    "automation": [
        ("build_script", "Build the automation script", []),
        ("smoke", "Smoke-test the script", ["build_script"]),
    ],
    "data_prep": [
        ("ingest", "Ingest and validate the input data", []),
        ("transform", "Transform into the requested deliverable", ["ingest"]),
    ],
}


def decompose_rule_based(job: Job) -> Plan:
    """Deterministic decomposition. Sub-task ids are namespaced by job id."""
    rule = _RULES[job.type]
    subtasks = [
        Subtask(
            id=f"{job.id}:{action}",
            title=title,
            action=action,
            depends_on=[f"{job.id}:{d}" for d in deps],
        )
        for (action, title, deps) in rule
    ]
    plan = Plan(subtasks=subtasks)
    validate_dag(plan.graph())  # guard: never emit an invalid/too-deep plan
    return plan


class Dispatcher:
    """Wraps decomposition. In mock mode (or without a key) it is purely
    rule-based; an LLM-backed path can be layered on for richer planning."""

    def __init__(self, use_llm: bool = False) -> None:
        self._use_llm = use_llm

    def plan(self, job: Job) -> Plan:
        # The LLM path is intentionally not used in the keyless mock pipeline;
        # rule-based decomposition is always the safe, validated fallback.
        return decompose_rule_based(job)
