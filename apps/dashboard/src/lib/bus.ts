// In-process pub/sub for SSE. /api/ingest publishes after a successful insert;
// /api/stream subscribes and pushes to connected clients. Single process, so a
// plain Set of listeners is sufficient — no external broker.

import type { IngestEvent } from "./types.ts";

export interface BusMessage {
  id: number;
  event: IngestEvent;
}

type Listener = (msg: BusMessage) => void;

const listeners = new Set<Listener>();

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function publish(msg: BusMessage): void {
  for (const fn of listeners) {
    try {
      fn(msg);
    } catch {
      // A failing subscriber must never break ingest or other subscribers.
    }
  }
}

export function subscriberCount(): number {
  return listeners.size;
}
