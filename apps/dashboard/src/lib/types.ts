// Data contract — the single shared vocabulary between the Python side
// (orchestrator + hooks) and the dashboard. Keep in lockstep with
// services/orchestrator/die_firma/models.py and BUILD_PROMPT §4.

/** Event kinds accepted by /api/ingest (strict allow-list). */
export const EVENT_KINDS = [
  "task_created",
  "task_updated",
  "subtask_created",
  "subtask_updated",
  "agent_assigned",
  "tool_call_start",
  "tool_call_end",
  "status_changed",
  "log",
  "token_usage",
  "cost_updated",
  "error",
  "escalation",
] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

/** Task / subtask status values (strict allow-list). */
export const STATUSES = [
  "queued",
  "planning",
  "running",
  "review",
  "blocked",
  "done",
  "failed",
  "cancelled",
  "awaiting_approval",
] as const;
export type Status = (typeof STATUSES)[number];

/** Terminal statuses a task can end up in. */
export const TERMINAL_STATUSES = ["done", "failed", "cancelled"] as const;

/** Agent roles. */
export const AGENTS = ["dispatcher", "worker", "reviewer", "sentinel"] as const;
export type Agent = (typeof AGENTS)[number];

/** Deliverable formats a job can request. */
export const DELIVERABLE_FORMATS = ["git_branch", "file", "report"] as const;
export type DeliverableFormat = (typeof DELIVERABLE_FORMATS)[number];

/** Job types used for routing. */
export const TASK_TYPES = ["code_gen", "code_review", "automation", "data_prep"] as const;
export type TaskType = (typeof TASK_TYPES)[number];

/** A raw ingest event as it arrives over HTTP (before validation). */
export interface IngestInput {
  kind: string;
  task_id?: unknown;
  subtask_id?: unknown;
  agent?: unknown;
  status?: unknown;
  message?: unknown;
  data?: unknown;
  tokens_in?: unknown;
  tokens_out?: unknown;
  cost_usd?: unknown;
  ts?: unknown;
}

/** A validated, normalised event ready to be persisted + projected. */
export interface IngestEvent {
  kind: EventKind;
  task_id: string | null;
  subtask_id: string | null;
  agent: Agent | null;
  status: Status | null;
  message: string | null;
  data: string | null; // JSON-serialised
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  ts: string; // ISO-8601
}

export interface TaskRow {
  id: string;
  type: string | null;
  priority: number | null;
  deadline: string | null;
  title: string | null;
  status: Status | null;
  agent: Agent | null;
  error: string | null;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  deliverable_format: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubtaskRow {
  id: string;
  task_id: string;
  title: string | null;
  status: Status | null;
  agent: Agent | null;
  depends_on: string | null; // JSON array of subtask ids
  created_at: string;
  updated_at: string;
}

export interface MetricsDailyRow {
  date: string; // YYYY-MM-DD
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  tasks_done: number;
  tasks_failed: number;
}
