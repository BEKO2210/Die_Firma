// Submit a new job by writing a Markdown file into inbox/ — the single source
// of truth for orchestration (prompt §1). This is the ONE place the dashboard
// writes to the filesystem; it never touches the read-model DB. The format is
// byte-for-byte the same as the `die-firma new` CLI command (cli.py::cmd_new),
// so the Python watcher parses it identically.

import path from "node:path";
import fs from "node:fs";
import crypto from "node:crypto";

// Mirror of services/orchestrator/.../models.py (allow-lists, kept in sync).
export const TASK_TYPES = ["code_gen", "code_review", "automation", "data_prep"] as const;
export const DELIVERABLE_FORMATS = ["git_branch", "file", "report"] as const;
export const PRIORITIES = [1, 2, 3] as const;

export type TaskType = (typeof TASK_TYPES)[number];
export type DeliverableFormat = (typeof DELIVERABLE_FORMATS)[number];

export interface JobInput {
  title: string;
  description: string;
  type: TaskType;
  priority: number;
  deliverable_format: DeliverableFormat;
  verify: string | null;
  requires_approval: boolean;
  days: number;
}

/** Where to drop job files. Explicit env wins; otherwise derive from the DB
 *  path (<root>/state/dashboard.db → <root>/inbox); else fall back to cwd. */
export function resolveInboxDir(): string {
  const fromEnv = process.env.DIE_FIRMA_INBOX_DIR;
  if (fromEnv !== undefined && fromEnv.trim() !== "") return path.resolve(fromEnv);
  const dbPath = process.env.DIE_FIRMA_DB_PATH;
  if (dbPath !== undefined && dbPath.trim() !== "") {
    return path.resolve(path.dirname(dbPath), "..", "inbox");
  }
  return path.resolve(process.cwd(), "..", "..", "inbox");
}

function asEnum<T extends string>(v: unknown, allowed: readonly T[], fallback: T): T {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : fallback;
}

/** Validate + normalise an untrusted request body into a JobInput.
 *  Returns a string describing the problem, or the cleaned input. */
export function parseJobInput(raw: unknown): { error: string } | { input: JobInput } {
  if (typeof raw !== "object" || raw === null) return { error: "body must be a JSON object" };
  const b = raw as Record<string, unknown>;

  const title = typeof b.title === "string" ? b.title.trim() : "";
  if (title === "") return { error: "title is required" };
  if (title.length > 200) return { error: "title too long (max 200 chars)" };

  const description = typeof b.description === "string" ? b.description.trim() : "";

  let verify: string | null = null;
  if (typeof b.verify === "string" && b.verify.trim() !== "") {
    verify = b.verify.trim();
    // The CLI wraps verify in double quotes inside YAML; forbid characters that
    // would break that single-line quoted scalar.
    if (/["\r\n]/.test(verify)) return { error: 'verify must not contain " or newlines' };
  }

  const priorityNum = typeof b.priority === "number" ? b.priority : Number(b.priority);
  const priority = (PRIORITIES as readonly number[]).includes(priorityNum) ? priorityNum : 2;

  const daysNum = typeof b.days === "number" ? b.days : Number(b.days);
  const days = Number.isInteger(daysNum) && daysNum > 0 && daysNum <= 365 ? daysNum : 7;

  return {
    input: {
      title,
      description,
      type: asEnum(b.type, TASK_TYPES, "code_gen"),
      priority,
      deliverable_format: asEnum(b.deliverable_format, DELIVERABLE_FORMATS, "file"),
      verify,
      requires_approval: b.requires_approval === true,
      days,
    },
  };
}

/** ISO-8601 with a +00:00 offset and no fractional seconds, matching Python's
 *  datetime.now(UTC).replace(microsecond=0).isoformat(). */
function deadlineIso(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setUTCMilliseconds(0);
  return d.toISOString().replace(".000Z", "+00:00");
}

/** Render the exact Markdown job file the CLI would write (cli.py::cmd_new). */
export function buildJobMarkdown(id: string, input: JobInput): string {
  const lines = [
    "---",
    `id: ${id}`,
    `type: ${input.type}`,
    `priority: ${input.priority}`,
    `deadline: ${deadlineIso(input.days)}`,
    `deliverable_format: ${input.deliverable_format}`,
    `requires_approval: ${input.requires_approval ? "true" : "false"}`,
  ];
  if (input.verify !== null) lines.push(`verify: "${input.verify}"`);
  lines.push("---", `# ${input.title}`, "", input.description || input.title, "");
  return lines.join("\n");
}

export interface CreatedJob {
  id: string;
  path: string;
  requires_approval: boolean;
}

/** Generate an id, write <id>.md into inbox/, and return what was created. */
export function writeJob(input: JobInput): CreatedJob {
  const id = crypto.randomUUID();
  const dir = resolveInboxDir();
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, `${id}.md`);
  fs.writeFileSync(dest, buildJobMarkdown(id, input), { encoding: "utf-8" });
  return { id, path: dest, requires_approval: input.requires_approval };
}
