"""Dispatcher: decompose a job into a shallow DAG of atomic sub-tasks.

Decomposition is delegated to a task plugin (see plugins.py) — the built-in
task types are themselves plugins. Deterministic rule-based decomposition is the
default and the guaranteed fallback if a plugin or the LLM dispatcher fails
(prompt §1: "deterministic rule fallback, if the dispatcher fails"). Every plan
is validated to be a DAG ≤2 levels deep.
"""

from __future__ import annotations

from pathlib import Path

from .models import Job, Plan
from .plugins import (
    BUILTIN_RULES,
    PluginRegistry,
    ValidationResult,
    build_plan,
    default_registry,
)


def decompose_rule_based(job: Job) -> Plan:
    """Deterministic decomposition from the built-in rules. Sub-task ids are
    namespaced by job id. Kept as the always-available safe fallback."""
    return build_plan(job, BUILTIN_RULES[job.type])


class Dispatcher:
    """Wraps decomposition. Consults the plugin registry for the job's task type
    and falls back to the built-in rule-based decomposition if no plugin handles
    it. In mock mode (or without a key) it is purely rule-based; an LLM-backed
    path can be layered on for richer planning."""

    def __init__(self, use_llm: bool = False, registry: PluginRegistry | None = None) -> None:
        self._use_llm = use_llm
        self._registry = registry or default_registry()

    def plan(self, job: Job) -> Plan:
        # The LLM path is intentionally not used in the keyless mock pipeline;
        # a registered plugin (or the rule-based fallback) is the safe default.
        plugin = self._registry.get(job.type)
        if plugin is not None:
            return plugin.decompose(job)
        return decompose_rule_based(job)

    def validate(self, job: Job, workdir: Path) -> ValidationResult:
        """Run the task plugin's extra acceptance check (review §1). Unknown
        types and plugins without a validator pass by default."""
        plugin = self._registry.get(job.type)
        if plugin is None:
            return ValidationResult(True, "no plugin")
        return plugin.validate(job, workdir)
