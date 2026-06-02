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
}

/**
 * Per-agent activity, aggregated from the event log (not from each task's
 * current agent — that always ends up "worker", which hid the dispatcher,
 * reviewer and sentinel entirely). `tasks` = distinct tasks the agent touched,
 * `active` = of those, the ones not yet terminal.
 */
export function agentStats(db: DB): AgentStat[] {
  return db
    .prepare(
      `SELECT e.agent AS agent,
              COUNT(DISTINCT e.task_id) AS tasks,
              COUNT(DISTINCT CASE
                WHEN t.status IS NULL OR t.status NOT IN ('done','failed','cancelled')
                THEN e.task_id END) AS active,
              CAST(COALESCE(SUM(e.tokens_in), 0) AS INTEGER)  AS tokens_in,
              CAST(COALESCE(SUM(e.tokens_out), 0) AS INTEGER) AS tokens_out,
              COALESCE(SUM(e.cost_usd), 0) AS cost_usd
         FROM events e
         LEFT JOIN tasks t ON t.id = e.task_id
        WHERE e.agent IS NOT NULL
        GROUP BY e.agent`,
    )
    .all() as AgentStat[];
}

/** Today's (UTC) accumulated spend — used by the orchestrator's cost guard. */
export function todaySpend(db: DB, day: string): { cost_usd: number; tokens_in: number; tokens_out: number } {
  const row = db.prepare("SELECT cost_usd, tokens_in, tokens_out FROM metrics_daily WHERE date = ?").get(day) as
    | Pick<MetricsDailyRow, "cost_usd" | "tokens_in" | "tokens_out">
    | undefined;
  return row ?? { cost_usd: 0, tokens_in: 0, tokens_out: 0 };
}
