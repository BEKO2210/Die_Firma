// Write-side endpoint for operator approvals. POST { id } to release a gated
// job (status `awaiting_approval`); we add the id to state/approved.json and the
// Python orchestrator lets it through on its next poll. Mirror of the CLI
// `die-firma approve <id>` command (cli.py::cmd_approve). Loopback-only, like
// every route here, so no auth token is required. Never writes the read-model DB.

import type { APIRoute } from "astro";
import { approveJob, isJobId } from "../../lib/approvals.ts";
import { json } from "../../lib/http.ts";

export const prerender = false;

export const POST: APIRoute = async ({ request }) => {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }

  const id = (raw as Record<string, unknown> | null)?.id;
  if (!isJobId(id)) return json({ error: "valid job id required" }, 400);

  try {
    const { approved } = approveJob(id);
    return json({ id, approved }, 200);
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to approve";
    return json({ error: message }, 500);
  }
};
