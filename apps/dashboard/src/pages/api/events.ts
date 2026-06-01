// Read-only: recent telemetry events for the live terminal view.

import type { APIRoute } from "astro";
import { getDb } from "../../lib/db.ts";
import { listEvents } from "../../lib/queries.ts";

export const prerender = false;

export const GET: APIRoute = ({ url }) => {
  const taskId = url.searchParams.get("task_id") ?? undefined;
  const limitParam = url.searchParams.get("limit");
  const limit = limitParam !== null ? Number(limitParam) : undefined;
  const events = listEvents(getDb(), {
    taskId,
    limit: Number.isFinite(limit) ? limit : undefined,
  });
  return new Response(JSON.stringify({ events }), {
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
};
