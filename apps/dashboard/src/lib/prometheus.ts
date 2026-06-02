// Prometheus / OpenMetrics text exporter (review §6). Renders the read-model
// projection into the Prometheus exposition format so long-term throughput,
// error rates and cost trends can be scraped, stored and graphed (Grafana).
// Pure render function + a thin DB collector; read-only, never writes the DB.

import type DatabaseType from "better-sqlite3";
import {
  agentStats,
  liveRates,
  statusCounts,
  todaySpend,
  type AgentStat,
  type LiveRates,
} from "./queries.ts";

type DB = DatabaseType.Database;

export interface PromSnapshot {
  statusCounts: Record<string, number>;
  agents: AgentStat[];
  live: LiveRates;
  todaySpend: { cost_usd: number; tokens_in: number; tokens_out: number };
}

/** Escape a Prometheus label value (backslash, double-quote, newline). */
function esc(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n");
}

function metric(
  lines: string[],
  name: string,
  help: string,
  type: "gauge" | "counter",
  samples: { labels?: Record<string, string>; value: number }[],
): void {
  lines.push(`# HELP ${name} ${help}`);
  lines.push(`# TYPE ${name} ${type}`);
  for (const s of samples) {
    const labels = s.labels
      ? "{" +
        Object.entries(s.labels)
          .map(([k, v]) => `${k}="${esc(v)}"`)
          .join(",") +
        "}"
      : "";
    lines.push(`${name}${labels} ${s.value}`);
  }
}

/** Render a snapshot into the Prometheus text exposition format. */
export function renderPrometheus(snap: PromSnapshot): string {
  const lines: string[] = [];

  metric(
    lines,
    "die_firma_tasks",
    "Number of tasks by current status.",
    "gauge",
    Object.entries(snap.statusCounts).map(([status, value]) => ({ labels: { status }, value })),
  );

  metric(lines, "die_firma_tokens_per_second", "Live token throughput (in+out).", "gauge", [
    { value: snap.live.tokens_per_sec },
  ]);
  metric(lines, "die_firma_events_per_second", "Live event rate.", "gauge", [
    { value: snap.live.events_per_sec },
  ]);
  metric(lines, "die_firma_active_tasks", "Tasks not yet in a terminal state.", "gauge", [
    { value: snap.live.active_tasks },
  ]);
  metric(lines, "die_firma_idle_seconds", "Seconds since the last event (-1 if none).", "gauge", [
    { value: snap.live.idle_sec ?? -1 },
  ]);

  metric(lines, "die_firma_today_cost_usd", "Accumulated spend today (UTC).", "gauge", [
    { value: snap.todaySpend.cost_usd },
  ]);
  metric(lines, "die_firma_today_tokens", "Tokens consumed today (UTC) by direction.", "gauge", [
    { labels: { direction: "in" }, value: snap.todaySpend.tokens_in },
    { labels: { direction: "out" }, value: snap.todaySpend.tokens_out },
  ]);

  metric(
    lines,
    "die_firma_agent_tokens_total",
    "Total tokens per agent by direction.",
    "counter",
    snap.agents.flatMap((a) => [
      { labels: { agent: a.agent, direction: "in" }, value: a.tokens_in },
      { labels: { agent: a.agent, direction: "out" }, value: a.tokens_out },
    ]),
  );
  metric(
    lines,
    "die_firma_agent_cost_usd_total",
    "Total cost per agent (USD).",
    "counter",
    snap.agents.map((a) => ({ labels: { agent: a.agent }, value: a.cost_usd })),
  );
  metric(
    lines,
    "die_firma_agent_active_tasks",
    "Non-terminal tasks each agent is currently touching.",
    "gauge",
    snap.agents.map((a) => ({ labels: { agent: a.agent }, value: a.active })),
  );

  return lines.join("\n") + "\n";
}

/** Collect a snapshot from the live DB and render it. `nowMs` is injectable. */
export function collectPrometheus(db: DB, nowMs: number = Date.now()): string {
  const today = new Date(nowMs).toISOString().slice(0, 10);
  return renderPrometheus({
    statusCounts: statusCounts(db),
    agents: agentStats(db),
    live: liveRates(db, nowMs),
    todaySpend: todaySpend(db, today),
  });
}
