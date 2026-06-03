# Changelog

All notable changes to **Die Firma** are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Acts on the second project review (operability, security, community).

### Added
- **License & community:** MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `ROADMAP.md`, GitHub issue/PR templates, CI + license badges.
- **Ingest hardening:** in-process token-bucket rate limiter (`429` +
  `RateLimit-*`/`Retry-After`) and strict same-origin check on `/api/ingest`.
- **Event-driven inbox watcher** (`watchdog`) with a polling fallback (replaces
  the 2s busy-poll); `watchdog` added as an optional `[watch]` extra + dev dep.
- **Dashboard error toasts** for backend/network failures (job submit, approval,
  chat), with i18n strings.
- **SQLite schema versioning** via `PRAGMA user_version` + a migration runner,
  plus write-tuning pragmas (`synchronous=NORMAL`, `busy_timeout=5000`) and an
  event read-index migration.
- **Automated release workflow** — builds the wheel + dashboard tarball and
  drafts a GitHub Release on `v*` tags.
- `docs/research-notes.md` documenting the (cited) best-practice basis.

### Changed
- **Executor factory** parameters grouped into typed `SandboxOptions` /
  `OllamaOptions` / `ClaudeOptions` bundles (no behaviour change).

## [0.2.0] — 2026-06-02

Implements the "next quality level" recommendations from the project review.

### Added
- **Task plugin architecture** (§1): `tasks/` discovery, `TaskPlugin` protocol,
  per-type decomposition + extra acceptance validators; the 4 built-in types are
  now plugins. Example plugin rejecting leftover TODO/FIXME placeholders.
- **Adaptive parallelism + job prioritisation** (§2): worker pool sized to live
  CPU load / free VRAM (`[concurrency].adaptive`); inbox processed most-urgent
  first by (priority, deadline).
- **Result cache** (§3): content-addressed replay of sub-task artifacts for
  identical inputs (`[cache]`).
- **LLM timeouts + fallback** (§4): configurable per-request timeout, fallback
  model on timeout/connection error, optional offline heuristic placeholder.
- **Internationalisation** (§5): i18n for the CLI (`die_firma/locales/`) and the
  dashboard (`src/lib/i18n.ts`), German + English, env/`config.toml` switch.
- **Observability** (§6): Prometheus exporter at `/api/metrics-prom`, a Grafana
  dashboard, a scrape config and an OpenTelemetry recipe (`docs/observability/`).
- **Mutation + chaos testing** (§7): `mutmut` / Stryker configs,
  `scripts/mutation.sh`, seeded chaos tests over the retry/sentinel path.
- **UI modernisation** (§8): light/dark theme toggle (persisted, no flash),
  keyboard `:focus-visible` styles, ARIA on new controls.
- **RAG enhancements** (§9): query expansion (multi-turn), context condensing to
  a char budget, and a pluggable `VectorStore` seam (Qdrant/Chroma-ready).
- **Packaging & deploy** (§10): pip/npm package metadata, Dockerfiles +
  `docker-compose.yml`, `scripts/check-updates.sh`, this changelog.

### Changed
- Orchestrator now runs a plugin-validation gate after the verify review.
- `OllamaExecutor` consults the result cache and the fallback path on each run.

## [0.1.0]

- Initial system: one-way dataflow, CQRS read-model dashboard, dispatcher /
  worker / reviewer / sentinel agents, quality pipeline (text + vision critique),
  model router, chat + RAG, mock/ollama/claude_code executors.

[0.2.0]: https://github.com/beko2210/die_firma/releases/tag/v0.2.0
[0.1.0]: https://github.com/beko2210/die_firma/releases/tag/v0.1.0
