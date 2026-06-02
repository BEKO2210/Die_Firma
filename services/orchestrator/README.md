# die-firma-orchestrator

The Python orchestration core of **Die Firma** — an autonomous local agency that
turns a Markdown job into a planned DAG of sub-tasks, runs them in
bounded/adaptive parallel, gates the result through a quality + plugin-validation
pipeline, and ships the deliverable. Telemetry is sent to the read-only
dashboard over HTTP; the filesystem (inbox/outbox/work) is the source of truth.

## Install

```bash
pip install -e ".[dev]"        # from services/orchestrator
```

## Use

```bash
die-firma new "Reverse a string" --type code_gen
die-firma run --once
```

Configuration lives in the repo-root `config.toml`; secrets come only from the
environment (`.env`). See the project [README](../../README.md) and
[CHANGELOG](../../CHANGELOG.md).

## Highlights

- Pluggable task types (`tasks/`), result cache, LLM timeouts + offline fallback
- Adaptive parallelism + job prioritisation
- i18n CLI output (`die_firma/locales/`)
- Local-first via Ollama; optional sandboxed Claude Code executor

MIT licensed.
