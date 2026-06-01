// Secret hardening (claude.md §6 / prompt §7): no working default secrets.
// Reject known placeholders and enforce a minimum-entropy / length floor. The
// dashboard side mirrors the Python startup check for the ingest token.

import crypto from "node:crypto";

// Known placeholder fragments that must never be accepted as a real secret.
const PLACEHOLDERS = [
  "changeme",
  "change-me",
  "bitte-ersetzen",
  "replace",
  "your-key-here",
  "your-token",
  "example",
  "placeholder",
  "todo",
  "xxx",
  "secret",
  "dummy",
];

const MIN_TOKEN_LENGTH = 24;

export interface SecretCheck {
  ok: boolean;
  reason?: string;
}

/** Validate a shared-secret style token: present, long enough, not a placeholder. */
export function checkToken(value: string | undefined): SecretCheck {
  if (value === undefined || value.trim() === "") {
    return { ok: false, reason: "missing" };
  }
  const v = value.trim();
  if (v.length < MIN_TOKEN_LENGTH) {
    return { ok: false, reason: `too short (< ${MIN_TOKEN_LENGTH} chars)` };
  }
  const lower = v.toLowerCase();
  for (const p of PLACEHOLDERS) {
    if (lower.includes(p)) return { ok: false, reason: `looks like a placeholder ("${p}")` };
  }
  // Crude entropy floor: require a mix of character classes.
  const classes = [/[a-z]/, /[A-Z0-9]/, /[-_]/].filter((re) => re.test(v)).length;
  if (classes < 2) return { ok: false, reason: "insufficient character variety" };
  return { ok: true };
}

/** The configured ingest token, or null when it fails the hardening check. */
export function getIngestToken(): string | null {
  const raw = process.env.DIE_FIRMA_INGEST_TOKEN;
  return checkToken(raw).ok ? (raw as string).trim() : null;
}

/** Constant-time comparison to avoid leaking the token via timing. */
export function tokenMatches(provided: string | null, expected: string): boolean {
  if (provided === null) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

/** Pull a bearer-style token from request headers. */
export function tokenFromRequest(req: Request): string | null {
  const direct = req.headers.get("x-die-firma-token");
  if (direct !== null && direct.trim() !== "") return direct.trim();
  const auth = req.headers.get("authorization");
  if (auth !== null && auth.toLowerCase().startsWith("bearer ")) {
    return auth.slice(7).trim();
  }
  return null;
}
