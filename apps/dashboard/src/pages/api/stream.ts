// Server-Sent Events stream of ingest activity. Read-only push channel; the UI
// also falls back to 2s polling (prompt §1). One ReadableStream per client.

import type { APIRoute } from "astro";
import { subscribe } from "../../lib/bus.ts";

export const prerender = false;

const HEARTBEAT_MS = 15_000;

export const GET: APIRoute = () => {
  const encoder = new TextEncoder();
  let unsubscribe: (() => void) | null = null;
  let heartbeat: ReturnType<typeof setInterval> | null = null;

  const teardown = () => {
    if (heartbeat !== null) clearInterval(heartbeat);
    if (unsubscribe !== null) unsubscribe();
    heartbeat = null;
    unsubscribe = null;
  };

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (data: string) => controller.enqueue(encoder.encode(data));

      // Initial comment + retry hint for EventSource reconnection.
      send(": connected\n");
      send("retry: 2000\n\n");

      unsubscribe = subscribe((msg) => {
        const payload = JSON.stringify({ id: msg.id, ...msg.event });
        send(`id: ${msg.id}\n`);
        send(`event: ${msg.event.kind}\n`);
        send(`data: ${payload}\n\n`);
      });

      heartbeat = setInterval(() => send(": ping\n\n"), HEARTBEAT_MS);
    },
    cancel() {
      teardown();
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
    },
  });
};
