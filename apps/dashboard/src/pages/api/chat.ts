// Chat endpoint: proxy a streaming conversation to the local Ollama server,
// optionally grounded with RAG context retrieved from outbox/ deliverables.
// Streams plain-text answer deltas back to the browser. Loopback only.

import type { APIRoute } from "astro";
import { json } from "../../lib/http.ts";
import { type ChatMessage, chatStream } from "../../lib/ollama.ts";
import { contextSystemPrompt, retrieve } from "../../lib/rag.ts";

export const prerender = false;

function cleanMessages(raw: unknown): ChatMessage[] | null {
  if (!Array.isArray(raw)) return null;
  const out: ChatMessage[] = [];
  for (const m of raw) {
    const role = (m as { role?: unknown })?.role;
    const content = (m as { content?: unknown })?.content;
    if ((role === "user" || role === "assistant" || role === "system") && typeof content === "string") {
      out.push({ role, content });
    }
  }
  return out.length ? out : null;
}

export const POST: APIRoute = async ({ request }) => {
  let body: Record<string, unknown> | null;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }

  const messages = cleanMessages(body?.messages);
  if (!messages) return json({ error: "messages[] required" }, 400);
  const model =
    typeof body.model === "string" && body.model.trim() !== "" ? body.model.trim() : "qwen2.5:14b";

  // Optional RAG: ground the answer in the most relevant outbox deliverables.
  let outgoing = messages;
  if (body.useRag === true) {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) {
      const hits = await retrieve(lastUser.content).catch(() => []);
      const sys = contextSystemPrompt(hits);
      if (sys) outgoing = [{ role: "system", content: sys }, ...messages];
    }
  }

  let upstream: Response;
  try {
    upstream = await chatStream(model, outgoing);
  } catch (err) {
    return json({ error: err instanceof Error ? err.message : "ollama unreachable" }, 502);
  }
  if (!upstream.ok || !upstream.body) return json({ error: `ollama ${upstream.status}` }, 502);

  // Transform Ollama's NDJSON stream into a plain-text delta stream.
  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buf = "";
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        const t = line.trim();
        if (!t) continue;
        try {
          const obj = JSON.parse(t) as { message?: { content?: string } };
          const c = obj.message?.content;
          if (c) controller.enqueue(encoder.encode(c));
        } catch {
          /* skip partial/non-JSON line */
        }
      }
    },
    cancel() {
      void reader.cancel();
    },
  });

  return new Response(stream, {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
  });
};
