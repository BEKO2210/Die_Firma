// Download a job's deliverables as a ZIP (review §UX). Read-only: it only reads
// outbox/<task>/ and streams a generated archive. Loopback like everything here.

import type { APIRoute } from "astro";
import fs from "node:fs";
import path from "node:path";
import { resolveOutboxDir } from "../../lib/rag.ts";
import { createZip, type ZipEntry } from "../../lib/zip.ts";

export const prerender = false;

/** A single safe path segment: no separators, no traversal. */
function safeSegment(id: string): boolean {
  return id !== "" && !id.includes("/") && !id.includes("\\") && !id.includes("..");
}

function collect(dir: string, base: string, out: ZipEntry[]): void {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    const rel = path.posix.join(base, entry.name);
    if (entry.isDirectory()) collect(full, rel, out);
    else if (entry.isFile()) out.push({ name: rel, data: new Uint8Array(fs.readFileSync(full)) });
  }
}

export const GET: APIRoute = ({ url }) => {
  const task = url.searchParams.get("task") ?? "";
  if (!safeSegment(task)) {
    return new Response(JSON.stringify({ error: "invalid task id" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }
  const dir = path.join(resolveOutboxDir(), task);
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
    return new Response(JSON.stringify({ error: "no deliverables for task" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  }

  const entries: ZipEntry[] = [];
  collect(dir, task, entries);
  const zip = createZip(entries);
  return new Response(zip, {
    status: 200,
    headers: {
      "content-type": "application/zip",
      "content-disposition": `attachment; filename="${task}.zip"`,
      "cache-control": "no-store",
    },
  });
};
