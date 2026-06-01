// Strict validation for /api/ingest — the single writer's gatekeeper.
// Pure, deterministic, dependency-free so it can be covered to 100% in unit
// tests. Allow-lists reject anything not explicitly permitted (fail-closed).

import {
  AGENTS,
  EVENT_KINDS,
  STATUSES,
  type Agent,
  type EventKind,
  type IngestEvent,
  type IngestInput,
  type Status,
} from "./types.ts";

const KIND_SET: ReadonlySet<string> = new Set(EVENT_KINDS);
const STATUS_SET: ReadonlySet<string> = new Set(STATUSES);
const AGENT_SET: ReadonlySet<string> = new Set(AGENTS);

// Kinds that are meaningless without a task they belong to. The remaining
// kinds (log, token_usage, cost_updated) may be global telemetry.
const REQUIRES_TASK_ID: ReadonlySet<EventKind> = new Set<EventKind>([
  "task_created",
  "task_updated",
  "subtask_created",
  "subtask_updated",
  "agent_assigned",
  "tool_call_start",
  "tool_call_end",
  "status_changed",
  "error",
  "escalation",
]);

const REQUIRES_SUBTASK_ID: ReadonlySet<EventKind> = new Set<EventKind>([
  "subtask_created",
  "subtask_updated",
]);

export type ValidationResult =
  | { ok: true; event: IngestEvent }
  | { ok: false; error: string };

function fail(error: string): ValidationResult {
  return { ok: false, error };
}

/** Optional non-empty string field; returns null when absent. */
function optString(value: unknown, field: string): string | null | { error: string } {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") return { error: `${field} must be a string` };
  const trimmed = value.trim();
  if (trimmed === "") return { error: `${field} must not be empty` };
  return trimmed;
}

/** Non-negative integer; default 0 when absent. */
function nonNegInt(value: unknown, field: string): number | { error: string } {
  if (value === undefined || value === null) return 0;
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return { error: `${field} must be an integer` };
  }
  if (value < 0) return { error: `${field} must be >= 0` };
  return value;
}

/** Non-negative finite float; default 0 when absent. */
function nonNegFloat(value: unknown, field: string): number | { error: string } {
  if (value === undefined || value === null) return 0;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return { error: `${field} must be a finite number` };
  }
  if (value < 0) return { error: `${field} must be >= 0` };
  return value;
}

function isErr(v: unknown): v is { error: string } {
  return typeof v === "object" && v !== null && "error" in v;
}

/**
 * Validate + normalise a raw ingest payload. The server fills `ts` with the
 * current time when absent; callers may pass a clock for determinism in tests.
 */
export function validateIngest(
  input: unknown,
  now: () => string = () => new Date().toISOString(),
): ValidationResult {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return fail("body must be a JSON object");
  }
  const raw = input as IngestInput;

  if (typeof raw.kind !== "string" || !KIND_SET.has(raw.kind)) {
    return fail(`kind must be one of: ${EVENT_KINDS.join(", ")}`);
  }
  const kind = raw.kind as EventKind;

  const taskId = optString(raw.task_id, "task_id");
  if (isErr(taskId)) return fail(taskId.error);
  if (REQUIRES_TASK_ID.has(kind) && taskId === null) {
    return fail(`task_id is required for kind "${kind}"`);
  }

  const subtaskId = optString(raw.subtask_id, "subtask_id");
  if (isErr(subtaskId)) return fail(subtaskId.error);
  if (REQUIRES_SUBTASK_ID.has(kind) && subtaskId === null) {
    return fail(`subtask_id is required for kind "${kind}"`);
  }

  let agent: Agent | null = null;
  if (raw.agent !== undefined && raw.agent !== null) {
    if (typeof raw.agent !== "string" || !AGENT_SET.has(raw.agent)) {
      return fail(`agent must be one of: ${AGENTS.join(", ")}`);
    }
    agent = raw.agent as Agent;
  }

  let status: Status | null = null;
  if (raw.status !== undefined && raw.status !== null) {
    if (typeof raw.status !== "string" || !STATUS_SET.has(raw.status)) {
      return fail(`status must be one of: ${STATUSES.join(", ")}`);
    }
    status = raw.status as Status;
  }

  const message = optString(raw.message, "message");
  if (isErr(message)) return fail(message.error);

  let data: string | null = null;
  if (raw.data !== undefined && raw.data !== null) {
    try {
      data = JSON.stringify(raw.data);
    } catch {
      return fail("data must be JSON-serialisable");
    }
    if (data === undefined) return fail("data must be JSON-serialisable");
  }

  const tokensIn = nonNegInt(raw.tokens_in, "tokens_in");
  if (isErr(tokensIn)) return fail(tokensIn.error);
  const tokensOut = nonNegInt(raw.tokens_out, "tokens_out");
  if (isErr(tokensOut)) return fail(tokensOut.error);
  const costUsd = nonNegFloat(raw.cost_usd, "cost_usd");
  if (isErr(costUsd)) return fail(costUsd.error);

  let ts: string;
  if (raw.ts === undefined || raw.ts === null) {
    ts = now();
  } else {
    if (typeof raw.ts !== "string") return fail("ts must be an ISO-8601 string");
    const parsed = Date.parse(raw.ts);
    if (Number.isNaN(parsed)) return fail("ts must be a valid ISO-8601 timestamp");
    ts = raw.ts;
  }

  return {
    ok: true,
    event: {
      kind,
      task_id: taskId,
      subtask_id: subtaskId,
      agent,
      status,
      message,
      data,
      tokens_in: tokensIn,
      tokens_out: tokensOut,
      cost_usd: costUsd,
      ts,
    },
  };
}

/** UTC calendar day (YYYY-MM-DD) of an ISO timestamp — the metrics_daily key. */
export function dayOf(iso: string): string {
  return iso.slice(0, 10);
}
