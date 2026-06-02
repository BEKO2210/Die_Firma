import { beforeEach, describe, expect, it } from "vitest";
import type Database from "better-sqlite3";
import { createDb } from "../src/lib/db.ts";
import { applyEvent } from "../src/lib/project.ts";
import { collectPrometheus, renderPrometheus } from "../src/lib/prometheus.ts";
import { statusCounts } from "../src/lib/queries.ts";
import type { IngestEvent } from "../src/lib/types.ts";

const TS = "2026-06-01T12:00:00.000Z";
function ev(p: Partial<IngestEvent> & { kind: IngestEvent["kind"] }): IngestEvent {
  return {
    task_id: null, subtask_id: null, agent: null, status: null, message: null,
    data: null, tokens_in: 0, tokens_out: 0, cost_usd: 0, ts: TS, ...p,
  };
}

let db: Database.Database;
beforeEach(() => {
  db = createDb(":memory:");
});

describe("prometheus exporter", () => {
  it("renders a pure snapshot into the exposition format", () => {
    const text = renderPrometheus({
      statusCounts: { running: 2, done: 5 },
      agents: [
        {
          agent: "worker", tasks: 3, active: 1, tokens_in: 100, tokens_out: 50,
          cost_usd: 0.25, last_kind: null, last_status: null, last_message: null, last_ts: null,
        },
      ],
      live: {
        window_sec: 60, tokens_per_sec: 1.5, tokens_in_per_sec: 1, tokens_out_per_sec: 0.5,
        events_per_sec: 0.2, active_tasks: 1, last_event_ts: TS, idle_sec: 3,
      },
      todaySpend: { cost_usd: 0.25, tokens_in: 100, tokens_out: 50 },
    });
    expect(text).toContain("# TYPE die_firma_tasks gauge");
    expect(text).toContain('die_firma_tasks{status="running"} 2');
    expect(text).toContain('die_firma_tasks{status="done"} 5');
    expect(text).toContain("die_firma_tokens_per_second 1.5");
    expect(text).toContain('die_firma_agent_tokens_total{agent="worker",direction="in"} 100');
    expect(text).toContain('die_firma_today_tokens{direction="out"} 50');
    expect(text.endsWith("\n")).toBe(true);
  });

  it("escapes label values", () => {
    const text = renderPrometheus({
      statusCounts: { 'a"b\\c': 1 },
      agents: [],
      live: {
        window_sec: 60, tokens_per_sec: 0, tokens_in_per_sec: 0, tokens_out_per_sec: 0,
        events_per_sec: 0, active_tasks: 0, last_event_ts: null, idle_sec: null,
      },
      todaySpend: { cost_usd: 0, tokens_in: 0, tokens_out: 0 },
    });
    expect(text).toContain('die_firma_tasks{status="a\\"b\\\\c"} 1');
    // idle_sec null -> -1 sentinel.
    expect(text).toContain("die_firma_idle_seconds -1");
  });

  it("status counts buckets NULL status as 'unknown'", () => {
    applyEvent(db, ev({ kind: "task_created", task_id: "t1", data: JSON.stringify({ priority: 2 }) }));
    applyEvent(db, ev({ kind: "status_changed", task_id: "t1", status: "done" }));
    applyEvent(db, ev({ kind: "task_created", task_id: "t2", data: JSON.stringify({ priority: 2 }) }));
    const counts = statusCounts(db);
    expect(counts.done).toBe(1);
    // t2 has no status yet.
    expect(counts.unknown ?? counts.queued).toBeGreaterThanOrEqual(1);
  });

  it("collects from a live DB without throwing", () => {
    applyEvent(db, ev({ kind: "token_usage", agent: "worker", tokens_in: 4, tokens_out: 6, cost_usd: 0.1 }));
    const text = collectPrometheus(db, Date.parse(TS));
    expect(text).toContain("die_firma_today_cost_usd");
    expect(text).toContain("die_firma_agent_tokens_total");
  });
});
