# Master-Build-Prompt — „Die Firma" (autonome digitale Agentur)

> **So nutzt du diesen Prompt:** Repo klonen (`git clone https://github.com/BEKO2210/Die_Firma`), in das Verzeichnis wechseln, `claude` starten und **diesen kompletten Text** als ersten Prompt einfügen. Die `claude.md` liegt bereits im Repo und ist die oberste Regelinstanz. Optional kannst du den Prompt als `docs/BUILD_PROMPT.md` ablegen.

---

## ROLLE & AUFTRAG

Du baust **„Die Firma"** — ein lokales, autonomes „digitale-Agentur"-System. Ich werfe Aufträge als Markdown-Dateien in `inbox/`. Das System zerlegt sie, führt sie aus, prüft das Ergebnis und liefert es ab — **vollautomatisch**.

**Das eiserne Prinzip:** Deterministischer Einweg-Datenfluss. Die KI-Agenten **rendern oder schreiben das Dashboard niemals**. Sie emittieren ausschließlich Telemetrie über Hooks. Das Dashboard ist eine **read-only Projektion** aus deterministischem Code.

---

## 0. ARBEITSREGELN (verbindlich)

1. **Lies zuerst `./claude.md`** und behandle sie als oberste, nicht verhandelbare Regelinstanz (Dependencies, Branch/PR-Hygiene, Verifikation, Tests, Secret-Härtung, Definition of Done). Bei Konflikt zwischen diesem Prompt und `claude.md` → **`claude.md` gewinnt**, frag im Zweifel nach.
2. **Arbeite in RUNS.** Lege `RUN_LOG.md` an und protokolliere jeden Run (Ziel, Schritte, Ergebnis, offene Punkte). Atomic Commits, **ein PR = ein Anliegen**.
3. **Verifiziere Versionen selbst.** Vor jedem Pin: `npm view <pkg> version` / `npm view <pkg> peerDependencies` bzw. `pip index versions <pkg>`. Trage exakte aufgelöste Versionen mit Datum in `DEPENDENCIES.md` ein. Die unten genannten Versionen sind der **verifizierte Stand vom 2026-06-01** und gelten als Untergrenze.
4. **Reproduzieren statt behaupten.** Nie „müsste jetzt gehen". Nach jeder Änderung neu bauen und gegen den **frischen Build** verifizieren. Fehlgeschlagen ist fehlgeschlagen — mit Ausgabe berichten.
5. **Frag nur bei sicherheits-/architekturkritischer Blockade.** Sonst mit den unten gelockten Defaults durcharbeiten.
6. Nutze dein eigenes Planungs-/Todo-System und gib am Ende jeder Phase einen kurzen Statusbericht.

---

## 1. GELOCKTE ARCHITEKTUR (final — nicht neu verhandeln)

**Scope & Modell**
- Hybride Tech-Tasks (Code-Gen, Code-Review, Pipeline-Automatisierung, Datenaufbereitung). Keine reinen Content-Tasks.
- Internes Solo-Tool, aber **API-First**, damit später Webhooks/Trigger andockbar sind.
- Rein funktional, kein Firmen-Branding. Technische Rollennamen.

**Auftragseingang**
- Datei-Drop `inbox/*.md` (YAML-Frontmatter) **+** CLI-Befehl. **Dateisystem = Single Source of Truth.**
- Pflichtfelder: `id` (UUID), `type` (enum), `priority` (1–3), `deadline` (ISO-Timestamp), `payload`, `deliverable_format`.
- Auftrag → **DAG** aus atomaren Sub-Tasks, **max. 2 Ebenen tief**.

**Agenten & Orchestrierung (4 Kern-Agenten)**
- **dispatcher** — Auftragsanalyse & Zerlegung in DAG.
- **worker** — Ausführung (Code/Recherche).
- **reviewer** — Test & Validierung.
- **sentinel** — Fehlerbehandlung, Retry, Loop-Breaker.
- Parallelität konfigurierbar, **Start: max. 2** parallele Tasks (Semaphore).
- Routing über `type`-Feld; deterministisches Regel-Fallback, falls Dispatcher scheitert.
- Voll-autonom; **Approval-Gate** nur bei `requires_approval: true` oder `priority: 1` → Stopp, manuelle CLI-Freigabe vor Merge.

**Execution-Engine**
- **worker = Claude Code headless** (`claude -p "<prompt>" --output-format stream-json`) pro Task, **unter `firejail`** mit Pfad-Whitelist. → native Claude-Code-Hooks feuern und liefern die Telemetrie.
- **dispatcher / reviewer / sentinel = Anthropic Python SDK** (strukturierte JSON-Antworten, **tiered models** günstiger). Deren Telemetrie kommt aus eigenen Lifecycle-Hooks (`PreExecution`/`PostExecution`/`OnError`).
- **Executor-Abstraktion** mit Modi `mock | claude_code` (per `config.toml`). `mock` ist deterministisch und erlaubt **Tests/E2E ohne API-Key**.

**Telemetrie & Datenfluss (das Herz)**
- `Hooks (Python) → HTTP POST /api/ingest → SQLite (WAL) → read-only UI`.
- **Genau ein Prozess besitzt die DB: die Node/Astro-App.** Python (Orchestrator + Worker + Hooks) **spricht ausschließlich HTTP**, schreibt **nie** direkt in die DB.
- **CQRS:** Dateisystem = SSoT der Orchestrierung; SQLite = reines Read-Model fürs Dashboard.
- `/api/ingest` ist der **einzige Writer** und **validiert strikt** (Allow-Lists für `kind`/`status`).
- Events: `task_created, task_updated, subtask_created, subtask_updated, agent_assigned, tool_call_start, tool_call_end, status_changed, log, token_usage, cost_updated, error, escalation`.

**Persistenz & Historie**
- SQLite via **better-sqlite3** (WAL, single writer).
- **Append-only Audit-Log** pro Auftrag im RUN_LOG-Stil (`runlog/<task_id>.log`) — wichtig fürs deterministische Debugging und spätere Finetuning-Datensätze.

**Dashboard**
- **Astro + TypeScript** (Node-Adapter, standalone). **read-only**, keine Schreib-Endpunkte außer `/api/ingest`.
- **Live-Update via SSE** (`/api/stream`), Fallback 2-Sekunden-Polling.
- Views: **Kanban** (Queue / In Progress / Review / Done), **Agenten-Monitor**, **Live-Terminal** (Telemetrie-Stream), **Metriken** (Token-Verbrauch, $-Kosten, Laufzeiten).
- Design: minimalistisch, Dark Mode, tabellarisch, Monospace für Logs/IDs. Hohe Informationsdichte.

**Fehler, Retry, Eskalation**
- Retry: **3 Versuche, exponential backoff** (2s/4s/8s). Danach Status `blocked`, Übergabe an `sentinel`.
- Eskalation: **rotes Flag** im Dashboard **+ Desktop-Notification** via `notify-send` (libnotify, Pop!_OS).

**Auslieferung**
- Ergebnisse nach `outbox/<id>/`, Status → `done`.
- Bei Code-Tasks zusätzlich automatischer lokaler Git-Commit auf neuem Branch `feature/task-<id>` **im Kopier-Repo** (nie in-place im Original; betroffene Repos werden in `work/<id>/` kopiert/geklont). Ich merge manuell.

**Betrieb, Sicherheit, Kosten**
- Hosting: isolierte **`systemd --user`-Services** + `loginctl enable-linger`. Kein root, kein Docker.
- Secrets: **`.env` + `.gitignore` + `.env.example`**. Beim Start: Mindest-Entropie-/Format-Check, **bekannte Platzhalter hart ablehnen** (`changeme` etc. → Abbruch).
- Alle Dienste/Ports an **`127.0.0.1`** binden, nie `0.0.0.0`. **Keine Auth** nötig, solange localhost-gebunden.
- **Hartes tägliches $-Kostenlimit.** `/api/ingest` summiert Tokens/Kosten pro Tag; Orchestrator fragt vor jedem Dispatch das Tageslimit ab und **pausiert die Queue** bei Erreichen. Tiered Models zur Kostensenkung.

---

## 2. TECH-STACK & PINS (verifizierter Stand 2026-06-01)

| Komponente | Version (Untergrenze) | Hinweis |
|---|---|---|
| Node.js | **24 LTS** | Active LTS bis 04/2028; Astro 6 braucht ≥22 |
| Astro | **^6.4.2** | mit `@astrojs/node` (standalone) |
| better-sqlite3 | **^12.10.0** | WAL nativ, Node 20–26 |
| @types/better-sqlite3 | **^7.6.13** | |
| TypeScript | neueste stabile 5.x | `strict` + `noUncheckedIndexedAccess` |
| Vitest | neueste stabile | Unit-Tests Dashboard |
| Python | **≥3.12** | `tomllib` stdlib |
| Pydantic | **^2.13.4** | Modelle/Validierung |
| anthropic (SDK) | neueste stabile | beim Install exakt erfassen |
| httpx | neueste stabile | HTTP-Client → ingest |
| ruff / mypy / pytest | neueste stabile | Lint / Typecheck / Test |

**Model-Defaults (Verfügbarkeit gegen `claude --model` und Anthropic-Docs prüfen, in `config.toml`):**
- `worker` → stärkstes verfügbares Opus-Modell
- `dispatcher` / `reviewer` → Sonnet-Tier
- `sentinel` → Haiku-Tier

---

## 3. MONOREPO-LAYOUT (Repo-Root)

```
Die_Firma/
├── claude.md                      # bereits vorhanden — oberste Regeln
├── README.md
├── DEPENDENCIES.md                # exakte Versionen + Datum
├── RUN_LOG.md
├── config.toml                    # Modelle, Limits, Concurrency, Pfade
├── .env.example
├── .gitignore
├── inbox/                         # Auftrags-Drop (SSoT)        [.gitkeep]
├── outbox/                        # fertige Deliverables         [.gitkeep]
├── work/                          # isolierte Task-Workdirs       [.gitkeep]
├── runlog/                        # append-only Audit-Log/Task    [.gitkeep]
├── state/                         # Orchestrator-State (json)     [.gitkeep]
├── apps/
│   └── dashboard/                 # Astro + TS — besitzt SQLite, ingest, SSE, UI
│       ├── package.json
│       ├── astro.config.mjs
│       ├── tsconfig.json
│       ├── src/
│       │   ├── lib/{db.ts, schema.sql, types.ts, bus.ts, validate.ts}
│       │   ├── pages/api/{ingest.ts, stream.ts, tasks.ts, events.ts, metrics.ts}
│       │   ├── pages/index.astro
│       │   └── components/*
│       └── tests/*                # vitest
├── services/
│   └── orchestrator/              # Python
│       ├── pyproject.toml
│       ├── die_firma/
│       │   ├── config.py models.py ingest_client.py
│       │   ├── watcher.py dispatcher.py worker.py reviewer.py sentinel.py
│       │   ├── orchestrator.py executor.py llm.py notify.py cli.py
│       └── tests/*                # pytest
├── hooks/                         # Claude-Code-Hooks (Python) → POST ingest
│   ├── common.py pre_tool_use.py post_tool_use.py stop.py subagent_stop.py
├── .claude/
│   └── settings.template.json     # verdrahtet Hooks für Worker-Sessions
├── scripts/{setup.sh, reset.sh, seed.py}
├── systemd/{die-firma-dashboard.service, die-firma-orchestrator.service}
└── .github/workflows/ci.yml
```

---

## 4. DATEN-VERTRAG (exakt umsetzen)

**Ingest-Event (POST `/api/ingest`, JSON):**
- `kind` (Pflicht, Allow-List s. o.)
- `task_id` (Pflicht für task-bezogene Events) · `subtask_id` (optional)
- `agent` (optional: dispatcher|worker|reviewer|sentinel)
- `status` (optional, Allow-List: `queued|planning|running|review|blocked|done|failed|cancelled|awaiting_approval`)
- `message` (optional) · `data` (optional, JSON) · `tokens_in`/`tokens_out` (int, optional) · `cost_usd` (float, optional) · `ts` (ISO, Server setzt falls leer)

**DB-Tabellen (better-sqlite3, WAL):**
- `events` — append-only: `id PK AUTOINCREMENT, task_id, subtask_id, kind, agent, status, message, data TEXT, tokens_in, tokens_out, cost_usd, ts`
- `tasks` — Projektion: `id PK, type, priority, deadline, title, status, agent, error, total_tokens_in, total_tokens_out, total_cost_usd, deliverable_format, created_at, updated_at`
- `subtasks` — `id PK, task_id, title, status, agent, depends_on TEXT(JSON), created_at, updated_at`
- `metrics_daily` — `date PK, tokens_in, tokens_out, cost_usd, tasks_done, tasks_failed`

`/api/ingest` schreibt **immer** nach `events` und projiziert daraus deterministisch in `tasks`/`subtasks`/`metrics_daily`. SSE-`bus` emittiert nach erfolgreichem Insert; `/api/stream` pusht an Clients.

**Auftrags-Frontmatter (`inbox/<id>.md`):**
```yaml
---
id: 0d4f...uuid
type: code_gen          # code_gen | code_review | automation | data_prep
priority: 2             # 1 (höchste, Approval-Gate) .. 3
deadline: 2026-06-05T18:00:00+02:00
deliverable_format: git_branch   # git_branch | file | report
requires_approval: false
allowed_paths:          # firejail-Whitelist; leer = nur work/<id>/
  - /home/belkis/projects/foo
verify: "npm test"      # optionales reproduzierbares Review-Kommando
---
# Aufgabenbeschreibung (Markdown frei)
...
```

---

## 5. QUALITÄTS-GATES (gemäß claude.md §3,4,8)

- TS `strict` + `noUncheckedIndexedAccess` ab Commit 1; Python `ruff` + `mypy --strict` (so weit praktikabel).
- **Coverage-Gate auf dem logikkritischen Kern** (Ziel 100 %): Ingest-Validierung/Projektion, DAG-Topologie, Retry/Backoff, Cost-Guard, Secret-Check.
- **Echte E2E mit `mock`-Executor** (kein Key): Auftrag in `inbox/` → vollständiger Flow → `outbox/` + Status `done` → Dashboard zeigt korrekt. DB **vor jedem Lauf zurücksetzen + frisch seeden**.
- Stabile Selektoren in UI-Tests; falls interaktive UI → **axe/WCAG-Gate**.
- CI-Gate: `npm audit --audit-level=high` + `pip-audit`, Lint, Typecheck, Unit (Coverage), E2E, Build — **alles grün vor „fertig"**.

---

## 6. BAU IN PHASEN (jede Phase = eigener Branch/PR, grün vor der nächsten)

- **Phase 0 — Fundament:** Layout, `config.toml`, `.env.example`, `.gitignore`, `DEPENDENCIES.md` (verifizierte Versionen + Datum), CI-Skeleton, `RUN_LOG.md`. Secret-Härtung als Startup-Check.
- **Phase 1 — Dashboard + DB + Ingest:** Astro/Node, `schema.sql`, `db.ts` (WAL, single writer), `validate.ts` (Allow-Lists), `/api/ingest`, Read-APIs, `/api/stream` (SSE), read-only Views. Vitest grün.
- **Phase 2 — Orchestrator-Kern + Mock-E2E:** `watcher` (Poll `inbox/`), `dispatcher` (DAG ≤2), `executor=mock`, `reviewer` (verify-Kommando), `orchestrator` (Semaphore, Statusmaschine), `ingest_client`, `cli` (`submit|approve|status|reset`). pytest + Mock-E2E grün.
- **Phase 3 — Claude-Code-Executor + Hooks + firejail:** `executor=claude_code` (spawnt `claude -p … --output-format stream-json` unter `firejail` mit Whitelist), `.claude/settings.template.json` verdrahtet die Hook-Skripte, Hook-Skripte posten Telemetrie. Lokaler Realtest mit echtem Key.
- **Phase 4 — Sentinel + Cost-Guard + Notify:** Retry/backoff, Loop-Breaker, `blocked`→Eskalation, Tages-$-Limit-Enforcement, `notify-send`, Approval-Gate.
- **Phase 5 — Betrieb + Doku + DoD:** `systemd --user`-Units, `setup.sh`/`reset.sh`/`seed.py`, README (Setup auf Pop!_OS, echte Keys), Definition-of-Done-Checkliste abhaken.

---

## 7. HARTE GUARDRAILS (niemals verletzen)

- Die KI/Agenten **rendern oder mutieren das Dashboard nie**; einziger Schreibpfad ist `/api/ingest`.
- **Kein direkter DB-Zugriff aus Python.** Nur HTTP.
- **Keine funktionierenden Default-Secrets.** Start bricht bei Platzhaltern ab.
- Alles an **`127.0.0.1`** binden.
- Worker laufen **sandboxed** (`firejail`) und sehen nur `work/<id>/` + explizite Whitelist.
- **Keine Tests abschwächen/skippen**, um grün zu werden. Keine Behauptungen ohne frischen Build.

---

## 8. DEFINITION OF DONE

- [ ] Neueste stabile Deps, `audit`/`pip-audit` sauber, Lockfiles konsistent.
- [ ] Lint + Typecheck + Unit (Coverage-Gate) + E2E (mock) + Build lokal grün.
- [ ] Frisch gebaut und gegen den neuen Build verifiziert.
- [ ] Fokussierte PRs von aktueller `main`, Konflikte sauber gelöst.
- [ ] `README.md`, `DEPENDENCIES.md`, `RUN_LOG.md` aktuell; Aussagen belegt (z. B. „verschlüsselt, NICHT extern auditiert"-Genauigkeit, wo relevant).
- [ ] Akzeptanz-E2E: Auftrag rein → automatisch verarbeitet → `outbox/` + `done` → Dashboard live korrekt.

---

## 9. JETZT STARTEN

1. Lies `./claude.md` vollständig und fasse die für diesen Build bindenden Punkte in `RUN_LOG.md` zusammen.
2. Verifiziere die aktuellen stabilen Versionen aus Abschnitt 2 und schreibe `DEPENDENCIES.md` (mit Datum).
3. Erstelle einen Phasenplan in deinem Todo-System und beginne mit **Phase 0**.
4. Committe atomar, halte nach jeder Phase an und gib mir einen kurzen Statusbericht, bevor du die nächste startest.

Wenn eine sicherheits- oder architekturkritische Mehrdeutigkeit auftaucht: **nachfragen statt raten**. Sonst: durcharbeiten mit den gelockten Defaults.
