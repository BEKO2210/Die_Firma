// Deterministic projection: given a validated IngestEvent, append it to the
// append-only `events` log and fold it into the tasks / subtasks /
// metrics_daily read-model. Pure SQL side-effects only; no I/O, no network.
// This is the second logic-critical core (100% coverage target).

import type DatabaseType from "better-sqlite3";
import { dayOf } from "./validate.ts";
import { TERMINAL_STATUSES, type IngestEvent, type Status, type TaskRow } from "./types.ts";

type DB = DatabaseType.Database;

const TERMINAL: ReadonlySet<string> = new Set(TERMINAL_STATUSES);

interface TaskCreateData {
  type?: unknown;
  priority?: unknown;
  deadline?: unknown;
  title?: unknown;
  deliverable_format?: unknown;
}

function parseData(json: string | null): Record<string, unknown> {
  if (json === null) return {};
  try {
    const v: unknown = JSON.parse(json);
    return typeof v === "object" && v !== null && !Array.isArray(v)
      ? (v as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function asString(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}

function asInt(v: unknown): number | null {
  return typeof v === "number" && Number.isInteger(v) ? v : null;
}

function getTask(db: DB, id: string): TaskRow | undefined {
  return db.prepare("SELECT * FROM tasks WHERE id = ?").get(id) as TaskRow | undefined;
}

function bumpDaily(
  db: DB,
  date: string,
  ev: IngestEvent,
  doneDelta: number,
  failedDelta: number,
): void {
  db.prepare(
    `INSERT INTO metrics_daily (date, tokens_in, tokens_out, cost_usd, tasks_done, tasks_failed)
     VALUES (@date, @tin, @tout, @cost, @done, @failed)
     ON CONFLICT(date) DO UPDATE SET
       tokens_in    = tokens_in    + @tin,
       tokens_out   = tokens_out   + @tout,
       cost_usd     = cost_usd     + @cost,
       tasks_done   = tasks_done   + @done,
       tasks_failed = tasks_failed + @failed`,
  ).run({
    date,
    tin: ev.tokens_in,
    tout: ev.tokens_out,
    cost: ev.cost_usd,
    done: doneDelta,
    failed: failedDelta,
  });
}

function projectTask(db: DB, ev: IngestEvent): void {
  const id = ev.task_id;
  if (id === null) return;
  const existing = getTask(db, id);
  const data = parseData(ev.data);

  if (existing === undefined) {
    // A task row is created by the task-level `task_created` event; never seed
    // task metadata from a stray sub-task event.
    const d: TaskCreateData = ev.subtask_id === null ? (data as TaskCreateData) : {};
    db.prepare(
      `INSERT INTO tasks (id, type, priority, deadline, title, status, agent, error,
         total_tokens_in, total_tokens_out, total_cost_usd, deliverable_format,
         created_at, updated_at)
       VALUES (@id, @type, @priority, @deadline, @title, @status, @agent, NULL,
         @tin, @tout, @cost, @fmt, @ts, @ts)`,
    ).run({
      id,
      type: asString(d.type),
      priority: asInt(d.priority),
      deadline: asString(d.deadline),
      title: asString(d.title),
      status: ev.status,
      agent: ev.agent,
      tin: ev.tokens_in,
      tout: ev.tokens_out,
      cost: ev.cost_usd,
      fmt: asString(d.deliverable_format),
      ts: ev.ts,
    });
    return;
  }

  // Update existing task. Sub-task events (those carrying a subtask_id) belong
  // to the SUB-task, not the parent: they may only contribute token/cost to the
  // task. Letting their title/status leak in is what made every card show the
  // last sub-task's title and flip the Kanban column to "done" mid-run. So task
  // title/metadata/status/agent are taken only from task-level events.
  const isTaskLevel = ev.subtask_id === null;
  const md: TaskCreateData = isTaskLevel ? (data as TaskCreateData) : {};
  const nextStatus: Status | null = isTaskLevel ? (ev.status ?? existing.status) : existing.status;
  const nextAgent = isTaskLevel ? (ev.agent ?? existing.agent) : existing.agent;
  const nextError = ev.kind === "error" ? (ev.message ?? existing.error) : existing.error;

  db.prepare(
    `UPDATE tasks SET
       type = COALESCE(@type, type),
       priority = COALESCE(@priority, priority),
       deadline = COALESCE(@deadline, deadline),
       title = COALESCE(@title, title),
       deliverable_format = COALESCE(@fmt, deliverable_format),
       status = @status,
       agent = @agent,
       error = @error,
       total_tokens_in = total_tokens_in + @tin,
       total_tokens_out = total_tokens_out + @tout,
       total_cost_usd = total_cost_usd + @cost,
       updated_at = @ts
     WHERE id = @id`,
  ).run({
    id,
    type: asString(md.type),
    priority: asInt(md.priority),
    deadline: asString(md.deadline),
    title: asString(md.title),
    fmt: asString(md.deliverable_format),
    status: nextStatus,
    agent: nextAgent,
    error: nextError,
    tin: ev.tokens_in,
    tout: ev.tokens_out,
    cost: ev.cost_usd,
    ts: ev.ts,
  });
}

function projectSubtask(db: DB, ev: IngestEvent): void {
  const id = ev.subtask_id;
  if (id === null || ev.task_id === null) return;
  const existing = db.prepare("SELECT * FROM subtasks WHERE id = ?").get(id);
  const data = parseData(ev.data);
  const dependsOn = Array.isArray(data.depends_on) ? JSON.stringify(data.depends_on) : null;
  const title = asString(data.title);

  if (existing === undefined) {
    db.prepare(
      `INSERT INTO subtasks (id, task_id, title, status, agent, depends_on, created_at, updated_at)
       VALUES (@id, @task_id, @title, @status, @agent, @depends_on, @ts, @ts)`,
    ).run({
      id,
      task_id: ev.task_id,
      title,
      status: ev.status,
      agent: ev.agent,
      depends_on: dependsOn,
      ts: ev.ts,
    });
    return;
  }

  db.prepare(
    `UPDATE subtasks SET
       title = COALESCE(@title, title),
       status = COALESCE(@status, status),
       agent = COALESCE(@agent, agent),
       depends_on = COALESCE(@depends_on, depends_on),
       updated_at = @ts
     WHERE id = @id`,
  ).run({
    id,
    title,
    status: ev.status,
    agent: ev.agent,
    depends_on: dependsOn,
    ts: ev.ts,
  });
}

/**
 * Apply one validated event: append to `events`, fold into projections, and
 * return the inserted event row id. Must be called inside a transaction by the
 * caller (the ingest endpoint wraps it).
 */
export function applyEvent(db: DB, ev: IngestEvent): number {
  const info = db
    .prepare(
      `INSERT INTO events (task_id, subtask_id, kind, agent, status, message, data,
         tokens_in, tokens_out, cost_usd, ts)
       VALUES (@task_id, @subtask_id, @kind, @agent, @status, @message, @data,
         @tokens_in, @tokens_out, @cost_usd, @ts)`,
    )
    .run(ev);

  // Detect a terminal transition for daily done/failed counters (count once).
  // Only task-level events count — otherwise each finished sub-task would also
  // bump "tasks done", massively over-counting the daily metric.
  let doneDelta = 0;
  let failedDelta = 0;
  if (
    ev.task_id !== null &&
    ev.subtask_id === null &&
    ev.status !== null &&
    TERMINAL.has(ev.status)
  ) {
    const prev = getTask(db, ev.task_id);
    const wasTerminal = prev !== undefined && prev.status !== null && TERMINAL.has(prev.status);
    if (!wasTerminal) {
      if (ev.status === "done") doneDelta = 1;
      else if (ev.status === "failed") failedDelta = 1;
    }
  }

  // Both projection helpers guard their own required ids internally.
  projectTask(db, ev);
  projectSubtask(db, ev);
  bumpDaily(db, dayOf(ev.ts), ev, doneDelta, failedDelta);

  return Number(info.lastInsertRowid);
}
