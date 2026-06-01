import { beforeEach, describe, expect, it } from "vitest";
import type Database from "better-sqlite3";
import { createDb } from "../src/lib/db.ts";
import { applyEvent } from "../src/lib/project.ts";
import type { IngestEvent, MetricsDailyRow, SubtaskRow, TaskRow } from "../src/lib/types.ts";

const TS = "2026-06-01T12:00:00.000Z";
const DAY = "2026-06-01";

function ev(p: Partial<IngestEvent> & { kind: IngestEvent["kind"] }): IngestEvent {
  return {
    task_id: null,
    subtask_id: null,
    agent: null,
    status: null,
    message: null,
    data: null,
    tokens_in: 0,
    tokens_out: 0,
    cost_usd: 0,
    ts: TS,
    ...p,
  };
}

let db: Database.Database;
const task = (id: string) => db.prepare("SELECT * FROM tasks WHERE id=?").get(id) as TaskRow | undefined;
const sub = (id: string) => db.prepare("SELECT * FROM subtasks WHERE id=?").get(id) as SubtaskRow | undefined;
const metric = (d: string) => db.prepare("SELECT * FROM metrics_daily WHERE date=?").get(d) as MetricsDailyRow | undefined;

beforeEach(() => {
  db = createDb(":memory:");
});

describe("applyEvent — events log + daily metrics", () => {
  it("appends events and returns incrementing ids", () => {
    const id1 = applyEvent(db, ev({ kind: "log", message: "a" }));
    const id2 = applyEvent(db, ev({ kind: "log", message: "b" }));
    expect(id2).toBe(id1 + 1);
    expect(db.prepare("SELECT COUNT(*) c FROM events").get()).toEqual({ c: 2 });
  });

  it("accumulates tokens/cost into metrics_daily (insert then ON CONFLICT update)", () => {
    applyEvent(db, ev({ kind: "token_usage", tokens_in: 10, tokens_out: 5, cost_usd: 0.1 }));
    applyEvent(db, ev({ kind: "token_usage", tokens_in: 2, tokens_out: 3, cost_usd: 0.2 }));
    expect(metric(DAY)).toMatchObject({ tokens_in: 12, tokens_out: 8 });
    expect(metric(DAY)!.cost_usd).toBeCloseTo(0.3, 6);
  });
});

describe("applyEvent — task projection", () => {
  it("creates a task from task_created with full data", () => {
    applyEvent(
      db,
      ev({
        kind: "task_created",
        task_id: "t1",
        status: "queued",
        agent: "dispatcher",
        tokens_in: 1,
        data: JSON.stringify({
          type: "code_gen",
          priority: 2,
          deadline: "2026-06-05T18:00:00Z",
          title: "Build X",
          deliverable_format: "git_branch",
        }),
      }),
    );
    expect(task("t1")).toMatchObject({
      id: "t1",
      type: "code_gen",
      priority: 2,
      deadline: "2026-06-05T18:00:00Z",
      title: "Build X",
      status: "queued",
      agent: "dispatcher",
      deliverable_format: "git_branch",
      total_tokens_in: 1,
      created_at: TS,
      updated_at: TS,
    });
  });

  it("creates a task with no/invalid data (null metadata branches)", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t2", data: "not-json" }));
    expect(task("t2")).toMatchObject({ type: null, priority: null, title: null, deliverable_format: null });
    // priority given as a float is rejected by asInt -> null
    applyEvent(db, ev({ kind: "task_created", task_id: "t3", data: JSON.stringify({ priority: 1.5, type: "" }) }));
    expect(task("t3")).toMatchObject({ priority: null, type: null });
  });

  it("updates an existing task: COALESCE metadata, overwrite status/agent, accumulate tokens", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", status: "queued", data: JSON.stringify({ title: "Orig" }) }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", status: "running", agent: "worker", tokens_in: 5, cost_usd: 0.5, ts: "2026-06-01T13:00:00.000Z" }));
    const t = task("t1")!;
    expect(t).toMatchObject({ title: "Orig", status: "running", agent: "worker", total_tokens_in: 5, updated_at: "2026-06-01T13:00:00.000Z" });
    expect(t.total_cost_usd).toBeCloseTo(0.5, 6);
  });

  it("keeps existing status/agent when an event omits them", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", status: "running", agent: "worker" }));
    applyEvent(db, ev({ kind: "log", task_id: "t1", message: "noise" }));
    expect(task("t1")).toMatchObject({ status: "running", agent: "worker" });
  });

  it("sets error only on error kind, preserves it otherwise", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", status: "running" }));
    applyEvent(db, ev({ kind: "error", task_id: "t1", message: "boom", status: "blocked" }));
    expect(task("t1")).toMatchObject({ error: "boom", status: "blocked" });
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", status: "running" }));
    expect(task("t1")!.error).toBe("boom"); // preserved by non-error kind
    // An error event with no message keeps the previous error (?? existing.error)
    applyEvent(db, ev({ kind: "error", task_id: "t1" }));
    expect(task("t1")!.error).toBe("boom");
  });

  it("treats a JSON array in data as empty metadata", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "arr", data: JSON.stringify([1, 2, 3]) }));
    expect(task("arr")).toMatchObject({ type: null, priority: null, title: null });
  });

  it("ignores task projection for global events (task_id null)", () => {
    applyEvent(db, ev({ kind: "token_usage", tokens_in: 3 }));
    expect(db.prepare("SELECT COUNT(*) c FROM tasks").get()).toEqual({ c: 0 });
  });
});

describe("applyEvent — terminal transitions count once", () => {
  it("counts done once even on repeated done events", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", status: "running" }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", status: "done" }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", status: "done" }));
    expect(metric(DAY)).toMatchObject({ tasks_done: 1, tasks_failed: 0 });
  });

  it("counts failed; cancelled counts neither", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "f1", status: "running" }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "f1", status: "failed" }));
    applyEvent(db, ev({ kind: "task_created", task_id: "c1", status: "running" }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "c1", status: "cancelled" }));
    expect(metric(DAY)).toMatchObject({ tasks_done: 0, tasks_failed: 1 });
  });

  it("handles a terminal event for a not-yet-existing task (prev undefined)", () => {
    applyEvent(db, ev({ kind: "status_changed", task_id: "new", status: "done" }));
    expect(metric(DAY)).toMatchObject({ tasks_done: 1 });
    expect(task("new")).toMatchObject({ status: "done" });
  });
});

describe("applyEvent — subtask projection", () => {
  it("creates and updates a subtask, coalescing depends_on", () => {
    applyEvent(db, ev({ kind: "subtask_created", task_id: "t1", subtask_id: "s1", status: "queued", data: JSON.stringify({ title: "Sub A", depends_on: ["s0"] }) }));
    expect(sub("s1")).toMatchObject({ task_id: "t1", title: "Sub A", status: "queued", depends_on: JSON.stringify(["s0"]) });
    applyEvent(db, ev({ kind: "subtask_updated", task_id: "t1", subtask_id: "s1", status: "done", agent: "worker" }));
    expect(sub("s1")).toMatchObject({ status: "done", agent: "worker", depends_on: JSON.stringify(["s0"]) });
  });

  it("ignores subtask projection when task_id is null", () => {
    applyEvent(db, ev({ kind: "log", subtask_id: "orphan" }));
    expect(sub("orphan")).toBeUndefined();
  });
});
