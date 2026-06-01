// Read-only: daily token/cost/throughput metrics + today's running total.
// The orchestrator polls this to enforce the hard daily cost limit.

import type { APIRoute } from "astro";
import { getDb } from "../../lib/db.ts";
import { listMetrics, todaySpend } from "../../lib/queries.ts";

export const prerender = false;

export const GET: APIRoute = () => {
  const db = getDb();
  const today = new Date().toISOString().slice(0, 10);
  return new Response(
    JSON.stringify({ today, today_spend: todaySpend(db, today), daily: listMetrics(db) }),
    { headers: { "content-type": "application/json", "cache-control": "no-store" } },
  );
};
