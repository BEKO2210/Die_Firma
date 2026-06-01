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

**Result:** Phase 0 scaffold in place. (Updated as the phase completes.)

**Open items:** Phases 1–5 to follow, each its own focused commit.
