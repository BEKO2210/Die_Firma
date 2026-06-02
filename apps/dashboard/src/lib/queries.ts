// Read-side queries over the projection. Pure DB reads (no writes), shared by
// the read API routes and unit tests.

import type DatabaseType from "better-sqlite3";
import type { MetricsDailyRow, SubtaskRow, TaskRow } from "./types.ts";

type DB = DatabaseType.Database;

export interface EventRow {
  id: number;
  task_id: string | null;
  subtask_id: string | null;
  kind: string;
  agent: string | null;
  status: string | null;
  message: string | null;
  data: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  ts: string;
}

export function listTasks(db: DB): TaskRow[] {
  return db.prepare("SELECT * FROM tasks ORDER BY priority ASC, created_at ASC").all() as TaskRow[];
}

/** Count of tasks grouped by status (NULL status bucketed as "unknown").
 * Used by the Prometheus exporter for a `die_firma_tasks{status=...}` gauge. */
export function statusCounts(db: DB): Record<string, number> {
  const rows = db
    .prepare("SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS c FROM tasks GROUP BY status")
    .all() as { status: string; c: number }[];
  const out: Record<string, number> = {};
  for (const r of rows) out[r.status] = r.c;
  return out;
}

export function listSubtasks(db: DB, taskId: string): SubtaskRow[] {
  return db
    .prepare("SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at ASC")
    .all(taskId) as SubtaskRow[];
}

export function listEvents(db: DB, opts: { taskId?: string; limit?: number } = {}): EventRow[] {
  const limit = Math.min(Math.max(opts.limit ?? 200, 1), 1000);
  if (opts.taskId !== undefined) {
    return db
      .prepare("SELECT * FROM events WHERE task_id = ? ORDER BY id DESC LIMIT ?")
      .all(opts.taskId, limit) as EventRow[];
  }
  return db.prepare("SELECT * FROM events ORDER BY id DESC LIMIT ?").all(limit) as EventRow[];
}

export function listMetrics(db: DB, limit = 30): MetricsDailyRow[] {
  return db
    .prepare("SELECT * FROM metrics_daily ORDER BY date DESC LIMIT ?")
    .all(Math.min(Math.max(limit, 1), 365)) as MetricsDailyRow[];
}

export interface AgentStat {
  agent: string;
  tasks: number;
  active: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  // Latest activity, so the monitor can show what each agent is doing *now*
  // (not just the worker). Derived from each agent's most recent event.
  last_kind: string | null;
  last_status: string | null;
  last_message: string | null;
  last_ts: string | null;
}

/**
 * Per-agent activity, aggregated from the event log (not from each task's
 * current agent — that always ends up "worker", which hid the dispatcher,
 * reviewer and sentinel entirely). `tasks` = distinct tasks the agent touched,
 * `active` = of those, the ones not yet terminal. Each row also carries that
 * agent's most recent event (kind/status/message/ts) for a live "current
 * action" readout.
 */
export function agentStats(db: DB): AgentStat[] {
  return db
    .prepare(
      `WITH agg AS (
         SELECT e.agent AS agent,
                COUNT(DISTINCT e.task_id) AS tasks,
                COUNT(DISTINCT CASE
                  WHEN t.status IS NULL OR t.status NOT IN ('done','failed','cancelled')
                  THEN e.task_id END) AS active,
                CAST(COALESCE(SUM(e.tokens_in), 0) AS INTEGER)  AS tokens_in,
                CAST(COALESCE(SUM(e.tokens_out), 0) AS INTEGER) AS tokens_out,
                COALESCE(SUM(e.cost_usd), 0) AS cost_usd,
                MAX(e.id) AS last_id
           FROM events e
           LEFT JOIN tasks t ON t.id = e.task_id
          WHERE e.agent IS NOT NULL
          GROUP BY e.agent
       )
       SELECT agg.agent, agg.tasks, agg.active, agg.tokens_in, agg.tokens_out,
              agg.cost_usd,
              le.kind AS last_kind, le.status AS last_status,
              le.message AS last_message, le.ts AS last_ts
         FROM agg
         JOIN events le ON le.id = agg.last_id`,
    )
    .all() as AgentStat[];
}

export interface LiveRates {
  window_sec: number;
  tokens_per_sec: number;
  tokens_in_per_sec: number;
  tokens_out_per_sec: number;
  events_per_sec: number;
  active_tasks: number;
  last_event_ts: string | null;
  idle_sec: number | null;
}

/**
 * Live throughput over a trailing wall-clock window, derived straight from the
 * append-only event log. Honest by construction: when nothing is happening the
 * window empties and every rate decays to 0 (no frozen "last known" values).
 * `nowMs` is injected so the function stays pure and testable.
 */
export function liveRates(db: DB, nowMs: number, windowSec = 60): LiveRates {
  const sinceIso = new Date(nowMs - windowSec * 1000).toISOString();
  const rows = db
    .prepare("SELECT tokens_in, tokens_out FROM events WHERE ts >= ?")
    .all(sinceIso) as Pick<EventRow, "tokens_in" | "tokens_out">[];

  let tin = 0;
  let tout = 0;
  for (const r of rows) {
    tin += r.tokens_in;
    tout += r.tokens_out;
  }

  const active = (
    db
      .prepare(
        "SELECT COUNT(*) AS c FROM tasks WHERE status IS NULL OR status NOT IN ('done','failed','cancelled')",
      )
      .get() as { c: number }
  ).c;

  const last = db.prepare("SELECT ts FROM events ORDER BY id DESC LIMIT 1").get() as
    | { ts: string }
    | undefined;
  const lastTs = last?.ts ?? null;
  const idle = lastTs ? Math.max(0, (nowMs - Date.parse(lastTs)) / 1000) : null;

  return {
    window_sec: windowSec,
    tokens_per_sec: (tin + tout) / windowSec,
    tokens_in_per_sec: tin / windowSec,
    tokens_out_per_sec: tout / windowSec,
    events_per_sec: rows.length / windowSec,
    active_tasks: active,
    last_event_ts: lastTs,
    idle_sec: idle,
  };
}

/** Today's (UTC) accumulated spend — used by the orchestrator's cost guard. */
export function todaySpend(db: DB, day: string): { cost_usd: number; tokens_in: number; tokens_out: number } {
  const row = db.prepare("SELECT cost_usd, tokens_in, tokens_out FROM metrics_daily WHERE date = ?").get(day) as
    | Pick<MetricsDailyRow, "cost_usd" | "tokens_in" | "tokens_out">
    | undefined;
  return row ?? { cost_usd: 0, tokens_in: 0, tokens_out: 0 };
}
