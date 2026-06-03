// The ONLY writer into the read-model (prompt §1/§7). Validates strictly,
// appends to the append-only event log, folds into projections in a single
// transaction, then publishes to the SSE bus.

import type { APIRoute } from "astro";
import { getDb } from "../../lib/db.ts";
import { applyEvent } from "../../lib/project.ts";
import { validateIngest } from "../../lib/validate.ts";
import { publish } from "../../lib/bus.ts";
import { getIngestToken, tokenFromRequest, tokenMatches } from "../../lib/secrets.ts";
import { allowedOrigins, ingestLimiter, originAllowed } from "../../lib/guard.ts";

export const prerender = false;

function json(body: unknown, status: number, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export const POST: APIRoute = async ({ request }) => {
  // Reject browser cross-origin attempts up front (no permissive CORS headers
  // are ever sent; a missing Origin = the server-side orchestrator client).
  if (!originAllowed(request.headers.get("origin"), allowedOrigins())) {
    return json({ ok: false, error: "forbidden origin" }, 403);
  }

  // Rate limit (safety valve against a runaway/looping producer).
  const rate = ingestLimiter.check();
  const rateHeaders = {
    "RateLimit-Limit": String(rate.limit),
    "RateLimit-Remaining": String(rate.remaining),
  };
  if (!rate.allowed) {
    return json({ ok: false, error: "rate limited" }, 429, {
      ...rateHeaders,
      "Retry-After": String(Math.ceil(rate.retryAfterMs / 1000)),
    });
  }

  const expected = getIngestToken();
  if (expected === null) {
    // Fail closed: refuse to ingest if the server has no valid shared secret.
    return json({ ok: false, error: "ingest token not configured" }, 503, rateHeaders);
  }
  if (!tokenMatches(tokenFromRequest(request), expected)) {
    return json({ ok: false, error: "unauthorized" }, 401, rateHeaders);
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid JSON body" }, 400);
  }

  const result = validateIngest(body);
  if (!result.ok) {
    return json({ ok: false, error: result.error }, 400);
  }

  const db = getDb();
  let id: number;
  try {
    id = db.transaction(() => applyEvent(db, result.event))();
  } catch (err) {
    return json({ ok: false, error: `persist failed: ${String(err)}` }, 500);
  }

  publish({ id, event: result.event });
  return json({ ok: true, id }, 201, rateHeaders);
};
