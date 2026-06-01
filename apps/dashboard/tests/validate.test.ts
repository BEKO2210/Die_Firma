import { describe, expect, it } from "vitest";
import { dayOf, validateIngest } from "../src/lib/validate.ts";

const clock = () => "2026-06-01T12:00:00.000Z";

function expectOk(input: unknown) {
  const r = validateIngest(input, clock);
  if (!r.ok) throw new Error(`expected ok, got error: ${r.error}`);
  return r.event;
}
function expectErr(input: unknown): string {
  const r = validateIngest(input, clock);
  if (r.ok) throw new Error("expected error, got ok");
  return r.error;
}

describe("validateIngest — shape & kind", () => {
  it("rejects non-objects", () => {
    expect(expectErr(null)).toMatch(/JSON object/);
    expect(expectErr([1, 2])).toMatch(/JSON object/);
    expect(expectErr("x")).toMatch(/JSON object/);
  });
  it("rejects unknown kind", () => {
    expect(expectErr({ kind: "nope" })).toMatch(/kind must be one of/);
    expect(expectErr({})).toMatch(/kind must be one of/);
  });
});

describe("validateIngest — task_id / subtask_id rules", () => {
  it("requires task_id for task-bound kinds", () => {
    expect(expectErr({ kind: "status_changed" })).toMatch(/task_id is required/);
  });
  it("requires subtask_id for subtask kinds", () => {
    expect(expectErr({ kind: "subtask_created", task_id: "t1" })).toMatch(/subtask_id is required/);
  });
  it("rejects non-string / empty ids", () => {
    expect(expectErr({ kind: "log", task_id: 5 })).toMatch(/task_id must be a string/);
    expect(expectErr({ kind: "log", task_id: "  " })).toMatch(/task_id must not be empty/);
    expect(expectErr({ kind: "log", subtask_id: 5 })).toMatch(/subtask_id must be a string/);
    expect(expectErr({ kind: "log", subtask_id: "" })).toMatch(/subtask_id must not be empty/);
  });
  it("allows global kinds without task_id", () => {
    const ev = expectOk({ kind: "log", message: "hi" });
    expect(ev.task_id).toBeNull();
    expect(ev.subtask_id).toBeNull();
  });
});

describe("validateIngest — enums", () => {
  it("rejects bad agent / status", () => {
    expect(expectErr({ kind: "log", agent: "boss" })).toMatch(/agent must be one of/);
    expect(expectErr({ kind: "log", agent: 1 })).toMatch(/agent must be one of/);
    expect(expectErr({ kind: "log", status: "spinning" })).toMatch(/status must be one of/);
    expect(expectErr({ kind: "log", status: 7 })).toMatch(/status must be one of/);
  });
  it("accepts valid agent / status / null", () => {
    const ev = expectOk({ kind: "log", agent: "worker", status: "running" });
    expect(ev.agent).toBe("worker");
    expect(ev.status).toBe("running");
    const ev2 = expectOk({ kind: "log", agent: null, status: null });
    expect(ev2.agent).toBeNull();
    expect(ev2.status).toBeNull();
  });
});

describe("validateIngest — message & data", () => {
  it("rejects non-string / empty message", () => {
    expect(expectErr({ kind: "log", message: 5 })).toMatch(/message must be a string/);
    expect(expectErr({ kind: "log", message: "   " })).toMatch(/message must not be empty/);
  });
  it("serialises data objects, rejects unserialisable", () => {
    const ev = expectOk({ kind: "log", data: { a: 1, b: [2, 3] } });
    expect(JSON.parse(ev.data as string)).toEqual({ a: 1, b: [2, 3] });
    // A bare function serialises to undefined -> rejected.
    expect(expectErr({ kind: "log", data: () => 1 })).toMatch(/JSON-serialisable/);
    // A circular structure throws inside JSON.stringify -> rejected.
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(expectErr({ kind: "log", data: circular })).toMatch(/JSON-serialisable/);
  });
  it("treats null data as absent", () => {
    expect(expectOk({ kind: "log", data: null }).data).toBeNull();
  });
});

describe("validateIngest — numbers", () => {
  it("rejects bad tokens_in/out and cost", () => {
    expect(expectErr({ kind: "log", tokens_in: 1.5 })).toMatch(/tokens_in must be an integer/);
    expect(expectErr({ kind: "log", tokens_in: -1 })).toMatch(/tokens_in must be >= 0/);
    expect(expectErr({ kind: "log", tokens_out: "5" })).toMatch(/tokens_out must be an integer/);
    expect(expectErr({ kind: "log", tokens_out: -2 })).toMatch(/tokens_out must be >= 0/);
    expect(expectErr({ kind: "log", cost_usd: Infinity })).toMatch(/finite number/);
    expect(expectErr({ kind: "log", cost_usd: "x" })).toMatch(/finite number/);
    expect(expectErr({ kind: "log", cost_usd: -0.5 })).toMatch(/cost_usd must be >= 0/);
  });
  it("defaults numbers to 0 and accepts valid", () => {
    const ev = expectOk({ kind: "log" });
    expect([ev.tokens_in, ev.tokens_out, ev.cost_usd]).toEqual([0, 0, 0]);
    const ev2 = expectOk({ kind: "log", tokens_in: 10, tokens_out: 20, cost_usd: 0.12 });
    expect([ev2.tokens_in, ev2.tokens_out, ev2.cost_usd]).toEqual([10, 20, 0.12]);
  });
});

describe("validateIngest — timestamp", () => {
  it("fills ts from clock when absent or null", () => {
    expect(expectOk({ kind: "log" }).ts).toBe(clock());
    expect(expectOk({ kind: "log", ts: null }).ts).toBe(clock());
  });
  it("rejects non-string / invalid ts, accepts valid", () => {
    expect(expectErr({ kind: "log", ts: 123 })).toMatch(/ts must be an ISO/);
    expect(expectErr({ kind: "log", ts: "not-a-date" })).toMatch(/valid ISO/);
    expect(expectOk({ kind: "log", ts: "2026-01-02T03:04:05Z" }).ts).toBe("2026-01-02T03:04:05Z");
  });
});

describe("validateIngest — default clock", () => {
  it("uses the real clock when no clock is injected", () => {
    const r = validateIngest({ kind: "log" });
    expect(r.ok).toBe(true);
    if (r.ok) expect(Number.isNaN(Date.parse(r.event.ts))).toBe(false);
  });
});

describe("dayOf", () => {
  it("extracts the UTC calendar day", () => {
    expect(dayOf("2026-06-01T23:59:59.000Z")).toBe("2026-06-01");
  });
});
