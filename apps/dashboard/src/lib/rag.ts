// Retrieval over the deliverables in outbox/ so the chat can answer questions
// about what the agency actually built. Text files are chunked and embedded
// with nomic-embed-text; the index is cached in-process and rebuilt when the
// outbox changes (cheap mtime signature). Read-only; never writes the DB.

import path from "node:path";
import fs from "node:fs";
import { cosine, embed } from "./ollama.ts";

export const EMBED_MODEL = "nomic-embed-text";

// Only embed human-readable deliverables; skip binaries and bulky lockfiles.
const TEXT_EXT = new Set([
  ".md", ".txt", ".html", ".htm", ".css", ".js", ".ts", ".jsx", ".tsx",
  ".json", ".py", ".sh", ".csv", ".yaml", ".yml", ".sql",
]);
const SKIP = new Set(["package-lock.json", "yarn.lock", "pnpm-lock.yaml"]);
const MAX_FILE_BYTES = 60_000;
const CHUNK_CHARS = 1200;

interface Chunk {
  file: string; // <job-id>/<relpath>
  text: string;
  vector: number[];
}

// Per-FILE cache keyed by absolute path, invalidated by a size+mtime signature.
// Only files that actually changed are re-embedded; everything else is reused,
// so adding one deliverable no longer re-embeds the whole corpus.
const fileCache = new Map<string, { sig: string; chunks: Chunk[] }>();

/** Where deliverables live. Mirrors resolveInboxDir() in jobs.ts. */
export function resolveOutboxDir(): string {
  const env = process.env.DIE_FIRMA_OUTBOX_DIR;
  if (env && env.trim() !== "") return path.resolve(env);
  const db = process.env.DIE_FIRMA_DB_PATH;
  if (db && db.trim() !== "") return path.resolve(path.dirname(db), "..", "outbox");
  return path.resolve(process.cwd(), "..", "..", "outbox");
}

function listTextFiles(root: string): string[] {
  if (!fs.existsSync(root)) return [];
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (TEXT_EXT.has(path.extname(entry.name)) && !SKIP.has(entry.name)) out.push(full);
    }
  };
  walk(root);
  return out.sort();
}

/** Cheap per-file change signature: size + mtime. */
function fileSig(file: string): string {
  const s = fs.statSync(file);
  return `${s.size}:${Math.round(s.mtimeMs)}`;
}

function chunkText(text: string): string[] {
  const chunks: string[] = [];
  for (let i = 0; i < text.length; i += CHUNK_CHARS) chunks.push(text.slice(i, i + CHUNK_CHARS));
  return chunks.length ? chunks : [""];
}

/** Embed every chunk of one file (the expensive Ollama round-trips). */
async function embedFile(file: string, rel: string): Promise<Chunk[]> {
  let raw: string;
  try {
    raw = fs.readFileSync(file, "utf-8").slice(0, MAX_FILE_BYTES);
  } catch {
    return [];
  }
  const chunks: Chunk[] = [];
  for (const piece of chunkText(raw)) {
    if (piece.trim() === "") continue;
    try {
      const vector = await embed(EMBED_MODEL, `${rel}\n\n${piece}`);
      if (vector.length) chunks.push({ file: rel, text: piece, vector });
    } catch {
      // Embedding unavailable (model not pulled / server down) -> skip; chat
      // still works without retrieval context.
    }
  }
  return chunks;
}

/** Build the index, re-embedding only files whose size/mtime changed. */
export async function buildIndex(): Promise<Chunk[]> {
  const root = resolveOutboxDir();
  const files = listTextFiles(root);
  const present = new Set(files);
  // Evict cache entries for deliverables that no longer exist.
  for (const cached of [...fileCache.keys()]) {
    if (!present.has(cached)) fileCache.delete(cached);
  }

  const all: Chunk[] = [];
  for (const file of files) {
    const sig = fileSig(file);
    const hit = fileCache.get(file);
    if (hit && hit.sig === sig) {
      all.push(...hit.chunks);
      continue;
    }
    const chunks = await embedFile(file, path.relative(root, file));
    fileCache.set(file, { sig, chunks });
    all.push(...chunks);
  }
  return all;
}

export interface Retrieved {
  file: string;
  text: string;
  score: number;
}

/** Top-k outbox chunks most similar to `query`. Empty if nothing is indexed. */
export async function retrieve(query: string, k = 4): Promise<Retrieved[]> {
  const chunks = await buildIndex();
  if (!chunks.length) return [];
  const q = await embed(EMBED_MODEL, query).catch(() => [] as number[]);
  if (!q.length) return [];
  return chunks
    .map((c) => ({ file: c.file, text: c.text, score: cosine(q, c.vector) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .filter((r) => r.score > 0.2);
}

/** Build a system message embedding the retrieved deliverable context. */
export function contextSystemPrompt(hits: Retrieved[]): string | null {
  if (!hits.length) return null;
  const ctx = hits
    .map((h) => `### Datei: ${h.file}\n${h.text}`)
    .join("\n\n");
  return (
    "Du bist der Assistent von „Die Firma\" und beantwortest Fragen zu den vom " +
    "System erzeugten Deliverables. Nutze NUR den folgenden Kontext, wenn er " +
    "relevant ist, und sage ehrlich, wenn etwas nicht im Kontext steht.\n\n" +
    `## Kontext aus outbox/\n${ctx}`
  );
}
