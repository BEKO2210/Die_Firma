// Shared JSON-response helper for the dashboard's API routes, so the response
// shape (content-type, no-store caching) is defined once instead of copy-pasted
// into every route. Loopback-only API; no auth/CORS headers needed.

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
