// Minimal Ollama HTTP helpers for the dashboard's chat + RAG features. The
// dashboard talks to the SAME local Ollama server the orchestrator uses; URL is
// configurable via DIE_FIRMA_OLLAMA_URL (defaults to localhost:11434). Loopback
// only, like every route here.

export function ollamaUrl(): string {
  const env = process.env.DIE_FIRMA_OLLAMA_URL;
  return (env && env.trim() !== "" ? env : "http://localhost:11434").replace(/\/+$/, "");
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

/** List installed models (name + size) from /api/tags. */
export async function listModels(): Promise<{ name: string; size: number }[]> {
  const res = await fetch(`${ollamaUrl()}/api/tags`);
  if (!res.ok) throw new Error(`ollama /api/tags ${res.status}`);
  const body = (await res.json()) as { models?: { name: string; size: number }[] };
  return (body.models ?? []).map((m) => ({ name: m.name, size: m.size }));
}

/** Single-text embedding via /api/embeddings. */
export async function embed(model: string, text: string): Promise<number[]> {
  const res = await fetch(`${ollamaUrl()}/api/embeddings`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model, prompt: text }),
  });
  if (!res.ok) throw new Error(`ollama /api/embeddings ${res.status}`);
  const body = (await res.json()) as { embedding?: number[] };
  return body.embedding ?? [];
}

/** Open a streaming /api/chat response (NDJSON). Returns the raw Response so the
 *  caller can pipe/transform the body. */
export async function chatStream(
  model: string,
  messages: ChatMessage[],
  signal?: AbortSignal,
): Promise<Response> {
  return fetch(`${ollamaUrl()}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ model, messages, stream: true }),
    signal,
  });
}

export function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    dot += a[i]! * b[i]!;
    na += a[i]! * a[i]!;
    nb += b[i]! * b[i]!;
  }
  return na && nb ? dot / (Math.sqrt(na) * Math.sqrt(nb)) : 0;
}
