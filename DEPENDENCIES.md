# DEPENDENCIES — verified versions

All versions resolved live with `npm view <pkg> version` / `pip index versions
<pkg>` per `claude.md §1` (never guessed from memory). Re-verify and bump the
date when these change.

**Verification date:** 2026-06-01
**Toolchain present in this build environment:** Node v22.22.2, npm 10.9.7,
Python 3.11.15, pip 24.0.

## Node / Dashboard (`apps/dashboard`)

| Package | Pinned (`^`) | Resolved 2026-06-01 | Notes |
|---|---|---|---|
| node | engines `>=22` | v22.22.2 | Astro 6 requires Node ≥22. Prompt targets Node 24 LTS; this container ships 22.22.2, which satisfies Astro's floor. Use Node 24 LTS in production. |
| astro | ^6.4.2 | 6.4.2 | standalone build via @astrojs/node |
| @astrojs/node | ^10.1.2 | 10.1.2 | `mode: "standalone"` adapter |
| better-sqlite3 | ^12.10.0 | 12.10.0 | WAL native, single writer |
| @types/better-sqlite3 | ^7.6.13 | 7.6.13 | |
| typescript | ^6.0.3 | 6.0.3 | **Discrepancy vs prompt:** prompt §2 said "neueste stabile 5.x". The latest stable is now **6.0.3**. Per `claude.md §1` (always newest stable) we pin 6.0.3. `strict` + `noUncheckedIndexedAccess` enabled. |
| vitest | ^4.1.8 | 4.1.8 | unit tests + coverage (`@vitest/coverage-v8`) |
| @types/node | ^25.9.1 | 25.9.1 | |

## Python / Orchestrator + Hooks (`services/orchestrator`, `hooks/`)

| Package | Pinned (`>=`) | Resolved 2026-06-01 | Notes |
|---|---|---|---|
| python | >=3.11 | 3.11.15 | **Discrepancy vs prompt:** prompt §2 said ">=3.12" (for `tomllib`). `tomllib` actually landed in **3.11**, and only 3.11.15 is available here, so the floor is set to 3.11. Use 3.12+ in production if available. |
| pydantic | >=2.13.4 | 2.13.4 | models / validation |
| anthropic | >=0.105.2 | 0.105.2 | SDK for dispatcher/reviewer/sentinel |
| httpx | >=0.28.1 | 0.28.1 | HTTP client → /api/ingest |
| pyyaml | >=6.0.3 | 6.0.3 | inbox frontmatter parsing |
| ruff | latest | 0.15.15 | lint + format |
| mypy | latest | 2.1.0 | typecheck (`--strict`) |
| pytest | latest | 9.0.3 | tests |
| pytest-cov | latest | 7.1.0 | coverage gate on logic-critical core |
| types-PyYAML | latest | 6.0.12.x | mypy stubs |

## Optional external runtimes (not Python/Node packages)

- **Ollama** (https://ollama.com) — the default `ollama` executor talks to a
  local Ollama server over HTTP (`/api/generate`) using `httpx` (already a
  dependency). No extra pip package is needed. Install Ollama separately and
  `ollama pull <model>` (default `llama3.2`). Fully local, no API key, $0 cost.
  Verified here against a stub Ollama server (real server not installed in CI).

## Known environment gaps (cannot be verified in this container)

- **firejail** is not installed → the `claude_code` executor's sandbox path
  (Phase 3) cannot be exercised here. Code is written fail-closed.
- **No ANTHROPIC_API_KEY** → real Claude runs (Phase 3) and the SDK agents are
  not exercised; the deterministic `mock` executor covers the full E2E flow.
- **notify-send / libnotify** and **systemd --user** (Phases 4–5) are
  Pop!_OS host facilities, not present here; their integration is documented
  but not run in CI.
