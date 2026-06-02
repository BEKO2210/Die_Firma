// Approve a gated job from the dashboard by writing its id into
// state/approved.json — byte-compatible with the Python ApprovalRegistry
// (services/orchestrator/.../watcher.py): a sorted JSON array of unique id
// strings. The orchestrator re-reads this file on every inbox poll, so a gated
// job stuck in `awaiting_approval` is released on the next tick. Like the rest
// of the dashboard write-side, this never touches the read-model DB.

import path from "node:path";
import fs from "node:fs";

/** The state/ dir, mirroring resolveDbPath() in db.ts
 *  (<root>/state/dashboard.db → <root>/state). */
export function resolveStateDir(): string {
  const fromEnv = process.env.DIE_FIRMA_DB_PATH;
  if (fromEnv && fromEnv.trim() !== "") return path.dirname(path.resolve(fromEnv));
  return path.resolve(process.cwd(), "state");
}

// Job ids are uuid4 (crypto.randomUUID() here / uuid4 in Python).
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isJobId(v: unknown): v is string {
  return typeof v === "string" && UUID_RE.test(v);
}

/** Add `id` to state/approved.json (idempotent). Reads the existing set,
 *  tolerating a missing or malformed file exactly like the Python reader, then
 *  writes the merged, sorted, de-duplicated array back. Returns the new set. */
export function approveJob(id: string): { approved: string[] } {
  const dir = resolveStateDir();
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, "approved.json");

  let ids = new Set<string>();
  try {
    const raw: unknown = JSON.parse(fs.readFileSync(dest, "utf-8"));
    if (Array.isArray(raw)) ids = new Set(raw.filter((x): x is string => typeof x === "string"));
  } catch {
    /* missing or malformed → start fresh, matching ApprovalRegistry */
  }

  ids.add(id);
  const sorted = [...ids].sort();
  fs.writeFileSync(dest, JSON.stringify(sorted), "utf-8");
  return { approved: sorted };
}
