// Ingest guards (review §5 / Top-10 #3): an in-process token-bucket rate limiter
// (a safety valve against a runaway/looping agent) and a strict same-origin
// check. Calibrated for a loopback, single-producer service — generous burst,
// no permissive CORS. `now` is injectable so the limiter is deterministically
// testable. Research basis: token bucket tolerates the bursts telemetry
// naturally produces; for loopback the bearer token is the real control and
// CORS headers are simply omitted (browsers block cross-origin reads by default).

export interface RateDecision {
  allowed: boolean;
  remaining: number;
  limit: number;
  /** Milliseconds until at least one token is available again (0 when allowed). */
  retryAfterMs: number;
}

/** A single refilling token bucket. */
export class TokenBucket {
  private tokens: number;
  private last: number;

  constructor(
    private readonly capacity: number,
    private readonly refillPerSec: number,
    nowMs: number,
  ) {
    this.tokens = capacity;
    this.last = nowMs;
  }

  take(nowMs: number, cost = 1): RateDecision {
    const elapsed = Math.max(0, (nowMs - this.last) / 1000);
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillPerSec);
    this.last = nowMs;
    if (this.tokens >= cost) {
      this.tokens -= cost;
      return { allowed: true, remaining: Math.floor(this.tokens), limit: this.capacity, retryAfterMs: 0 };
    }
    const deficit = cost - this.tokens;
    const retryAfterMs = Math.ceil((deficit / this.refillPerSec) * 1000);
    return { allowed: false, remaining: 0, limit: this.capacity, retryAfterMs };
  }
}

/** Token-bucket limiter keyed by an arbitrary string (e.g. "global"). */
export class RateLimiter {
  private readonly buckets = new Map<string, TokenBucket>();

  constructor(
    private readonly capacity: number,
    private readonly refillPerSec: number,
    private readonly now: () => number = Date.now,
  ) {}

  check(key = "global", cost = 1): RateDecision {
    const nowMs = this.now();
    let bucket = this.buckets.get(key);
    if (!bucket) {
      bucket = new TokenBucket(this.capacity, this.refillPerSec, nowMs);
      this.buckets.set(key, bucket);
    }
    return bucket.take(nowMs, cost);
  }
}

/**
 * Is the request's Origin acceptable? The legitimate producer (the Python
 * orchestrator) is a server-side client and sends no Origin header, so a missing
 * Origin is allowed. A present Origin means a browser cross-origin attempt — it
 * is only allowed if it exactly matches the configured dashboard origin.
 */
export function originAllowed(origin: string | null, allowed: string[]): boolean {
  if (origin === null || origin.trim() === "") return true; // non-browser client
  return allowed.includes(origin.trim());
}

/** Allowed origins from the configured dashboard URL (loopback) + localhost. */
export function allowedOrigins(): string[] {
  const out = new Set<string>();
  const url = process.env.DIE_FIRMA_DASHBOARD_URL;
  if (url) {
    try {
      out.add(new URL(url).origin);
    } catch {
      /* ignore malformed URL */
    }
  }
  const port = process.env.PORT ?? "4321";
  out.add(`http://127.0.0.1:${port}`);
  out.add(`http://localhost:${port}`);
  return [...out];
}

/** Read a numeric env var, falling back when unset or non-finite. */
export function numEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  const n = raw === undefined ? NaN : Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

// Default ingest limiter: a high ceiling (burst) with a steady refill, so
// legitimate telemetry bursts never trip it but a runaway loop is capped.
// Override via env for tuning.
export const ingestLimiter = new RateLimiter(
  numEnv("DIE_FIRMA_INGEST_BURST", 600),
  numEnv("DIE_FIRMA_INGEST_RATE", 100),
);
