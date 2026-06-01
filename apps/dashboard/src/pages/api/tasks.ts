// Read-only: tasks grouped for the Kanban board, with their subtasks.

import type { APIRoute } from "astro";
import { getDb } from "../../lib/db.ts";
import { listSubtasks, listTasks } from "../../lib/queries.ts";

export const prerender = false;

export const GET: APIRoute = () => {
  const db = getDb();
  const tasks = listTasks(db).map((t) => ({ ...t, subtasks: listSubtasks(db, t.id) }));
  return new Response(JSON.stringify({ tasks }), {
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
};
