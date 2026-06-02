# `tasks/` — custom task plugins (review §1)

Every `*.py` file in this directory is imported at orchestrator startup and may
register a **task plugin**: a custom decomposition strategy plus an optional
extra acceptance check. This lets you extend what the agency can do without
touching the orchestrator core.

## The contract

A plugin satisfies `die_firma.plugins.TaskPlugin`:

```python
class TaskPlugin(Protocol):
    task_type: str
    def decompose(self, job: Job) -> Plan: ...
    def validate(self, job: Job, workdir: Path) -> ValidationResult: ...
```

- `decompose(job)` turns a job into a shallow (≤2-level) DAG of sub-tasks.
- `validate(job, workdir)` runs *after* the deliverable is produced (and after
  the `verify` command). Return `ValidationResult(False, "why")` to fail the job.

The quickest way to build one is `RuleBasedPlugin`: a static decomposition rule
plus a `validator` callable (see `example_no_placeholders.py`).

## Registering

A module is discovered if it exposes **either**:

- a `register(registry)` function (called with the live `PluginRegistry`), **or**
- a module-level `PLUGIN` attribute (registered with `replace=True`, so it can
  override a built-in task type's behaviour).

## Adding a brand-new task type

The four built-in types (`code_gen`, `code_review`, `automation`, `data_prep`)
are part of the read-model contract shared with the dashboard
(`Job.type` in `models.py` and `TaskType` in `apps/dashboard/src/lib/types.ts`).
To add a genuinely new type end-to-end:

1. add it to the `TaskType` literal in both `models.py` and `types.ts`, then
2. drop a plugin here whose `task_type` is the new name.

Overriding the decomposition/validation of an existing type needs **only** a
plugin here — no core change.
