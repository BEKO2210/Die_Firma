// Prometheus scrape endpoint (review §6): the read-model projection exported in
// the Prometheus text exposition format. Loopback-only like the rest of the
// dashboard; read-only. Point a Prometheus job at GET /api/metrics-prom.

import type { APIRoute } from "astro";
import { getDb } from "../../lib/db.ts";
import { collectPrometheus } from "../../lib/prometheus.ts";

export const prerender = false;

export const GET: APIRoute = () => {
  const body = collectPrometheus(getDb());
  return new Response(body, {
    headers: {
      "content-type": "text/plain; version=0.0.4; charset=utf-8",
      "cache-control": "no-store",
    },
  });
};
