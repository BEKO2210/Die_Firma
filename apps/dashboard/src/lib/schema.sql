-- Die Firma read-model schema (better-sqlite3, WAL, single writer).
-- events is append-only; tasks/subtasks/metrics_daily are deterministic
-- projections recomputed by /api/ingest. See BUILD_PROMPT §4.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     TEXT,
  subtask_id  TEXT,
  kind        TEXT NOT NULL,
  agent       TEXT,
  status      TEXT,
  message     TEXT,
  data        TEXT,
  tokens_in   INTEGER NOT NULL DEFAULT 0,
  tokens_out  INTEGER NOT NULL DEFAULT 0,
  cost_usd    REAL NOT NULL DEFAULT 0,
  ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS tasks (
  id                 TEXT PRIMARY KEY,
  type               TEXT,
  priority           INTEGER,
  deadline           TEXT,
  title              TEXT,
  status             TEXT,
  agent              TEXT,
  error              TEXT,
  total_tokens_in    INTEGER NOT NULL DEFAULT 0,
  total_tokens_out   INTEGER NOT NULL DEFAULT 0,
  total_cost_usd     REAL NOT NULL DEFAULT 0,
  deliverable_format TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS subtasks (
  id          TEXT PRIMARY KEY,
  task_id     TEXT NOT NULL,
  title       TEXT,
  status      TEXT,
  agent       TEXT,
  depends_on  TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id);

CREATE TABLE IF NOT EXISTS metrics_daily (
  date         TEXT PRIMARY KEY,
  tokens_in    INTEGER NOT NULL DEFAULT 0,
  tokens_out   INTEGER NOT NULL DEFAULT 0,
  cost_usd     REAL NOT NULL DEFAULT 0,
  tasks_done   INTEGER NOT NULL DEFAULT 0,
  tasks_failed INTEGER NOT NULL DEFAULT 0
);
