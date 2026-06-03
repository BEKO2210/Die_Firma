import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  AGENTS,
  DELIVERABLE_FORMATS,
  EVENT_KINDS,
  STATUSES,
  TASK_TYPES,
  TERMINAL_STATUSES,
} from "../src/lib/types.ts";

// Drift guard: the dashboard's vocabulary must match the canonical
// contracts/task-types.json (shared with the Python orchestrator).
const contract = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../contracts/task-types.json"), "utf-8"),
) as Record<string, string[]>;

describe("shared contract", () => {
  it("task types match", () => {
    expect([...TASK_TYPES]).toEqual(contract.task_types);
  });
  it("deliverable formats match", () => {
    expect([...DELIVERABLE_FORMATS]).toEqual(contract.deliverable_formats);
  });
  it("agents match", () => {
    expect([...AGENTS]).toEqual(contract.agents);
  });
  it("statuses match", () => {
    expect([...STATUSES]).toEqual(contract.statuses);
  });
  it("terminal statuses match", () => {
    expect([...TERMINAL_STATUSES]).toEqual(contract.terminal_statuses);
  });
  it("event kinds match", () => {
    expect([...EVENT_KINDS]).toEqual(contract.event_kinds);
  });
});
