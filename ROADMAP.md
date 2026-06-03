# Roadmap

Die Firma is local-first and pre-1.0. This roadmap captures the planned
direction and is prioritised from the project reviews. Status legend:
✅ done · 🟡 in progress · ⬜ planned.

## Recently shipped (v0.2)

✅ Task plugin architecture · ✅ adaptive parallelism + job priority ·
✅ result cache · ✅ LLM timeouts + fallback · ✅ i18n (de/en) ·
✅ Prometheus/Grafana observability · ✅ mutation + chaos tests ·
✅ light/dark theme + a11y · ✅ RAG query expansion + vector-store seam ·
✅ packaging + Docker Compose. See [`CHANGELOG.md`](CHANGELOG.md).

## Now (low effort, high value)

- ✅ OSS **license** (MIT) + `CONTRIBUTING.md` + issue/PR templates + CI badge.
- ✅ **Ingest API hardening** — in-process rate limiter + strict CORS posture +
  constant-time token compare.
- ✅ Inbox **file-watcher** (replaces busy-poll; polling kept as fallback).
- ✅ Dashboard **error toasts** + i18n error strings.
- ✅ **SQLite schema versioning** via `PRAGMA user_version` + a migration runner.
- ✅ Automated **release workflow** (build artifacts on tag).

## Next (structural)

- ⬜ **HMAC-signed ingest** with timestamp + short TTL (replay protection) for
  any non-loopback deployment; token rotation helper.
- ⬜ **Executor refactor** — collapse the factory's parameter list behind a
  typed `ExecutorConfig`/builder; one class per mode with a shared interface.
- ⬜ **Shared task-type schema** — single source of truth (JSON Schema) that
  generates both the Python `Literal` and the TS union, removing the two-place
  edit.
- ⬜ **Release automation to registries** — publish the wheel to PyPI and the
  dashboard image to GHCR on tag.

## Later (ambitious / multi-user & scale)

These intentionally go beyond the current single-writer, local-first design and
will only be pursued if the project moves toward multi-user/cloud use:

- ⬜ **Distributed queue/event bus** (NATS/Redis Streams) to decouple telemetry
  from the dashboard process and allow multiple worker instances.
- ⬜ **Client-server DB** (PostgreSQL) when more than one ingest writer is
  needed; until then SQLite (WAL) is the right tool for a single writer.
- ⬜ **Multi-user mode** — login, per-user job ownership, RBAC, audit logs.
- ⬜ **Cloud executor platform** — more model providers (GPT-4o etc.), API-key
  management, cost controls, pluggable tools.
- ⬜ **Plugin marketplace** — installable third-party task plugins.
- ⬜ **Desktop app** — Electron dashboard bundling the backend for non-devs.

Have an idea or want to pick something up? See [`CONTRIBUTING.md`](CONTRIBUTING.md).
