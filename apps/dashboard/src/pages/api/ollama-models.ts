// Read-only: list chat-capable models installed on the local Ollama server, so
// the chat panel can offer a model switcher. The embedding model is filtered
// out (not usable for chat). Loopback only.

import type { APIRoute } from "astro";
import { json } from "../../lib/http.ts";
import { listModels } from "../../lib/ollama.ts";

export const prerender = false;

export const GET: APIRoute = async () => {
  try {
    const models = await listModels();
    const chat = models
      .map((m) => m.name)
      .filter((n) => !n.includes("embed") && !n.includes("nomic"));
    return json({ models: chat });
  } catch (err) {
    return json({ models: [], error: err instanceof Error ? err.message : "unreachable" });
  }
};
