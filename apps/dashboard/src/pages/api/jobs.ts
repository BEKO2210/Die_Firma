// Write-side endpoint for human-submitted jobs. POST a job spec; we drop a
// Markdown file into inbox/ (the orchestration source of truth) and the Python
// orchestrator picks it up on its next poll. This does NOT write the read-model
// DB — that stays owned solely by /api/ingest. Loopback-only, like every other
// route here, so no auth token is required.

import type { APIRoute } from "astro";
import { parseJobInput, writeJob } from "../../lib/jobs.ts";

export const prerender = false;

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

export const POST: APIRoute = async ({ request }) => {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }

  const parsed = parseJobInput(raw);
  if ("error" in parsed) return json({ error: parsed.error }, 400);

  try {
    const created = writeJob(parsed.input);
    return json(
      { id: created.id, requires_approval: created.requires_approval, path: created.path },
      201,
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "failed to write job";
    return json({ error: message }, 500);
  }
};
