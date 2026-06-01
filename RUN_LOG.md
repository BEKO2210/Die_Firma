# RUN_LOG

Append-only run journal (prompt §0.2). One entry per run: goal, steps,
result, open items. Atomic commits, one PR = one concern.

---

## Binding rules distilled from `claude.md` (oberste Regelinstanz)

- **§1 Deps/Security:** always newest stable, record date; check peerDeps
  before bumps; `audit`/`pip-audit` as CI gate (`--audit-level=high`), goal 0
  high/critical; fix transitive issues via overrides + regenerate lockfile.
- **§2 Branch/PR:** branch from current `main`; one PR = one concern; never
  hand-resolve lockfile conflicts; green full CI locally before push.
- **§3 Verify, don't claim:** reproduce before fixing; never weaken/skip
  tests; rebuild before testing (no stale build); report failures honestly.
- **§4 Tests/Quality:** strict typing + `noUncheckedIndexedAccess` from commit
  1; coverage gate on security/logic-critical core (goal 100%); real E2E
  flows; a11y gate for UI; lint + format in CI.
- **§5 Deterministic scripts:** reset + freshly seed DB each run; stable
  selectors; read values before masking; clean start/stop of bg services.
- **§6 Config/secret hardening:** no working default secrets (reject known
  placeholders → abort); secrets from env with entropy/format check; bind
  services to `127.0.0.1`; dev/prod split.
- **§7 Honest docs:** only provable security claims; docs match real code.
- **§8 Definition of Done:** newest deps + clean audit + consistent lockfile;
  lint+typecheck+unit(coverage)+E2E+(a11y)+build green; fresh build verified;
  branch from main, focused PR; docs/changelog updated.

**Conflict rule:** if BUILD_PROMPT and `claude.md` disagree, `claude.md` wins.

---

## Run 1 — 2026-06-01 — Phase 0 (Fundament)

**Goal:** Repo scaffold, locked config, secret hardening groundwork, verified
dependency pins, CI skeleton.

**Environment verified:** Node v22.22.2, npm 10.9.7, Python 3.11.15, pip 24.0.
`firejail` absent, no API key, no systemd/notify-send → Phases 3–5 host
facilities documented but not runnable here (see DEPENDENCIES.md).

**Steps:**
1. Read `claude.md`; distilled binding rules above.
2. Verified live versions (`npm view`, `pip index versions`) → `DEPENDENCIES.md`
   with date 2026-06-01. Noted TS 6.0.3 (not 5.x) and Python 3.11 (not 3.12)
   discrepancies vs prompt and resolved them per claude.md "newest stable".
3. Created monorepo layout per prompt §3 with `.gitkeep` in runtime dirs.
4. Wrote `.gitignore`, `.env.example` (placeholder secrets, no working
   defaults), `config.toml` (locked architecture), CI skeleton.

**Result:** Phase 0 scaffold in place.

---

## Run 2 — 2026-06-01 — Phase 1 (Dashboard + DB + Ingest)

**Goal:** Astro/Node dashboard owning SQLite (WAL, single writer), strict
`/api/ingest` validation + deterministic projection, SSE stream, read-only UI.

**Steps:** types/schema/db (schema embedded via `?raw`), `validate.ts` (fail-
closed allow-lists), `project.ts` (events → tasks/subtasks/metrics_daily),
`secrets.ts` (token hardening), bus + read queries, API routes, dark dense UI
with SSE + 2s polling fallback, vitest incl. axe a11y.

**Result:** 46 tests green; 100% coverage on validate/project/secrets/queries;
`astro check` 0 errors; build OK; live-server smoke test (401/400/201 +
correct projection through read APIs). TS pinned to 6.0.3 (latest stable, not
the 5.x the prompt mentioned) per claude.md §1.

## Run 3 — 2026-06-01 — Phase 2 (Orchestrator core + Mock E2E)

**Goal:** Python orchestrator, keyless deterministic flow, full mock E2E.

**Steps:** core modules (dag/retry/cost/secrets) at 100%; config (tomllib +
.env + secret check); models; watcher; rule-based dispatcher (DAG ≤2);
executor abstraction (mock | claude_code, firejail builder); reviewer;
sentinel (retry+escalation); ingest_client (HTTP only); delivery (outbox +
unsigned `feature/task-<id>` branch); orchestrator state machine; CLI; scripts.

**Result:** ruff + ruff format + mypy --strict clean; pytest 57 passing at 94%
(core 100%); `scripts/e2e.sh` green (job → orchestrator → outbox + dashboard
status `done`). Python floor set to 3.11 (only 3.11.15 available; `tomllib`
present) instead of the prompt's 3.12, per claude.md §1.

## Run 4 — 2026-06-01 — Phase 3 (Claude Code executor + hooks + firejail)

**Goal:** Real worker path + native-hook telemetry wiring.

**Steps:** `hooks/{common,pre_tool_use,post_tool_use,stop,subagent_stop}.py`
(stdlib-only, POST to /api/ingest, never break the worker);
`.claude/settings.template.json` (`__HOOKS_DIR__` substitution); executor now
provisions each worker session (writes `.claude/settings.json`, exports task/
subtask identity + ingest token/url) and runs `claude … --output-format
stream-json` under firejail.

**Result:** 63 tests green; 94% coverage. **Not runnable in this container**:
no `firejail`, no real `ANTHROPIC_API_KEY` → the real worker path is built
fail-closed and documented but exercised only on a Pop!_OS host.

## Run 5 — 2026-06-01 — Phases 4 + 5 (Sentinel/cost/notify/approval + Ops/Doku)

**Goal:** Finish guardrails + operations + Definition of Done.

**Steps:** Phase-4 pieces were already implemented and tested in Phase 2/3
(retry/backoff + loop-breaker → `blocked` + `escalation` + `notify-send`;
hard daily cost guard pauses the queue; `priority:1`/`requires_approval`
approval gate). Phase 5: `systemd --user` units (loopback, no root, hardened),
README operations + DoD checklist, finalized DEPENDENCIES/RUN_LOG.

**Result:** All local gates green (see README DoD). Host-only facilities
(firejail, real key, systemd, notify-send) documented, not CI-verified.

**Open items:** real-host validation of Phases 3–5 (firejail sandbox, live
Claude worker, systemd services, desktop notifications).
