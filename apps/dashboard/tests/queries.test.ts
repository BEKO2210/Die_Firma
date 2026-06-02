import { beforeEach, describe, expect, it } from "vitest";
import type Database from "better-sqlite3";
import { createDb } from "../src/lib/db.ts";
import { applyEvent } from "../src/lib/project.ts";
import { agentStats, listEvents, listMetrics, liveRates, listSubtasks, listTasks, todaySpend } from "../src/lib/queries.ts";
import type { IngestEvent } from "../src/lib/types.ts";

const TS = "2026-06-01T12:00:00.000Z";
function ev(p: Partial<IngestEvent> & { kind: IngestEvent["kind"] }): IngestEvent {
  return { task_id: null, subtask_id: null, agent: null, status: null, message: null, data: null, tokens_in: 0, tokens_out: 0, cost_usd: 0, ts: TS, ...p };
}

let db: Database.Database;
beforeEach(() => {
  db = createDb(":memory:");
});

describe("read queries", () => {
  it("lists tasks ordered by priority then created_at, with subtasks", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "low", data: JSON.stringify({ priority: 3 }) }));
    applyEvent(db, ev({ kind: "task_created", task_id: "high", data: JSON.stringify({ priority: 1 }) }));
    applyEvent(db, ev({ kind: "subtask_created", task_id: "high", subtask_id: "s1" }));
    const tasks = listTasks(db);
    expect(tasks.map((t) => t.id)).toEqual(["high", "low"]);
    expect(listSubtasks(db, "high").map((s) => s.id)).toEqual(["s1"]);
    expect(listSubtasks(db, "low")).toEqual([]);
  });

  it("lists events newest-first, filterable by task, with clamped limits", () => {
    applyEvent(db, ev({ kind: "log", task_id: "t1", message: "1" }));
    applyEvent(db, ev({ kind: "log", task_id: "t2", message: "2" }));
    applyEvent(db, ev({ kind: "log", task_id: "t1", message: "3" }));
    expect(listEvents(db).map((e) => e.message)).toEqual(["3", "2", "1"]);
    expect(listEvents(db, { taskId: "t1" }).map((e) => e.message)).toEqual(["3", "1"]);
    // limit clamps: 0 -> min 1
    expect(listEvents(db, { limit: 0 }).length).toBe(1);
    expect(listEvents(db, { limit: 99999 }).length).toBe(3);
  });

  it("lists metrics and reports today's spend (present + absent)", () => {
    applyEvent(db, ev({ kind: "token_usage", tokens_in: 4, tokens_out: 6, cost_usd: 0.25 }));
    expect(listMetrics(db).length).toBe(1);
    expect(todaySpend(db, "2026-06-01")).toMatchObject({ tokens_in: 4, tokens_out: 6 });
    expect(todaySpend(db, "1999-01-01")).toEqual({ cost_usd: 0, tokens_in: 0, tokens_out: 0 });
  });

  it("aggregates per-agent activity from the event log", () => {
    // dispatcher plans (0 tokens), worker does the LLM work (tokens), on one task.
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", agent: "dispatcher", status: "queued" }));
    applyEvent(db, ev({ kind: "tool_call_end", task_id: "t1", agent: "worker", tokens_in: 10, tokens_out: 5 }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", agent: "worker", status: "done" }));
    const byName = new Map(agentStats(db).map((a) => [a.agent, a]));
    // dispatcher touched the task but burned no tokens — previously invisible.
    expect(byName.get("dispatcher")).toMatchObject({ tasks: 1, active: 0, tokens_in: 0 });
    // worker's tokens are attributed to the worker; task is terminal -> not active.
    expect(byName.get("worker")).toMatchObject({ tasks: 1, active: 0, tokens_in: 10, tokens_out: 5 });
  });

  it("computes live throughput inside the window and decays to zero outside it", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", status: "running" }));
    applyEvent(db, ev({ kind: "tool_call_end", task_id: "t1", agent: "worker", tokens_in: 30, tokens_out: 90 }));

    // 10s after the events -> within a 60s window.
    const live = liveRates(db, Date.parse(TS) + 10_000, 60);
    expect(live.tokens_per_sec).toBeCloseTo(120 / 60);
    expect(live.tokens_out_per_sec).toBeCloseTo(90 / 60);
    expect(live.active_tasks).toBe(1);
    expect(live.idle_sec).toBeGreaterThanOrEqual(0);

    // 2min later -> events fall out of the window, every rate is 0.
    const stale = liveRates(db, Date.parse(TS) + 120_000, 60);
    expect(stale.tokens_per_sec).toBe(0);
    expect(stale.events_per_sec).toBe(0);
  });
});
