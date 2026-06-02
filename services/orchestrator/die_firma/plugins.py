"""Task plugins: a registry that makes task types extensible (review §1).

The built-in task types (code_gen, code_review, automation, data_prep) are
themselves plugins, defined by a small rule. A plugin owns two things:

  * ``decompose(job)`` — turn a job into a shallow DAG of sub-tasks;
  * ``validate(job, workdir)`` — an optional extra acceptance check run after the
    deliverable is produced (e.g. "the report must mention every finding", "the
    extracted CSV must be non-empty").

New task behaviours can be added by dropping a Python module into a ``tasks/``
directory and registering a plugin there — no change to the orchestrator core.
The registry is dependency-free and deterministic so it stays unit-testable.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .dag import validate_dag
from .models import Job, Plan, Subtask

# (action, title, [dep-actions]) — the shape of a single decomposition step.
RuleStep = tuple[str, str, list[str]]

# Built-in decomposition rules. Each stays within the 2-level DAG depth limit.
BUILTIN_RULES: dict[str, list[RuleStep]] = {
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


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a plugin's extra acceptance check."""

    passed: bool
    detail: str = ""


@runtime_checkable
class TaskPlugin(Protocol):
    """Structural contract for a task-type handler.

    ``task_type`` is a read-only property so frozen-dataclass plugins (and any
    plain attribute) satisfy the protocol."""

    @property
    def task_type(self) -> str: ...
    def decompose(self, job: Job) -> Plan: ...
    def validate(self, job: Job, workdir: Path) -> ValidationResult: ...


def build_plan(job: Job, rule: Sequence[RuleStep]) -> Plan:
    """Turn a decomposition rule into a validated, id-namespaced Plan."""
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
    validate_dag(plan.graph())  # never emit an invalid / too-deep plan
    return plan


@dataclass(frozen=True)
class RuleBasedPlugin:
    """A plugin defined by a static decomposition rule plus an optional
    ``validate`` hook. Built-ins use this; custom plugins may too."""

    task_type: str
    rule: list[RuleStep]
    validator: Callable[[Job, Path], ValidationResult] | None = None

    def decompose(self, job: Job) -> Plan:
        return build_plan(job, self.rule)

    def validate(self, job: Job, workdir: Path) -> ValidationResult:
        if self.validator is None:
            return ValidationResult(True, "no extra validation")
        return self.validator(job, workdir)


class PluginRegistry:
    """Maps a task type to its plugin. First registration wins unless replaced."""

    def __init__(self) -> None:
        self._plugins: dict[str, TaskPlugin] = {}

    def register(self, plugin: TaskPlugin, *, replace: bool = False) -> None:
        if not isinstance(plugin, TaskPlugin):  # pragma: no cover - defensive
            raise TypeError(f"{plugin!r} is not a TaskPlugin")
        if plugin.task_type in self._plugins and not replace:
            raise ValueError(f"task type {plugin.task_type!r} already registered")
        self._plugins[plugin.task_type] = plugin

    def get(self, task_type: str) -> TaskPlugin | None:
        return self._plugins.get(task_type)

    def types(self) -> list[str]:
        return sorted(self._plugins)


def default_registry() -> PluginRegistry:
    """A registry pre-loaded with the four built-in task types."""
    reg = PluginRegistry()
    for task_type, rule in BUILTIN_RULES.items():
        reg.register(RuleBasedPlugin(task_type, rule))
    return reg


def load_plugins_from_dir(directory: Path, registry: PluginRegistry) -> list[str]:
    """Import every ``*.py`` in ``directory`` and let it self-register.

    Each module may expose either ``register(registry)`` (called with the live
    registry) or a module-level ``PLUGIN`` attribute (registered with
    ``replace=True`` so a custom plugin can override a built-in). Returns the
    list of task types added/overridden. Missing directory -> no-op."""
    added: list[str] = []
    if not directory.is_dir():
        return added
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod_name = f"die_firma_tasks_{path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:  # pragma: no cover - import edge
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        before = set(registry.types())
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            register_fn(registry)
        plugin = getattr(module, "PLUGIN", None)
        if plugin is not None:
            registry.register(plugin, replace=True)
        added.extend(sorted(set(registry.types()) - before))
    return added
