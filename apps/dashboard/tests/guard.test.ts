import { afterEach, describe, expect, it } from "vitest";
import { RateLimiter, TokenBucket, allowedOrigins, numEnv, originAllowed } from "../src/lib/guard.ts";

describe("TokenBucket", () => {
  it("allows up to capacity then blocks with a retry hint", () => {
    const b = new TokenBucket(2, 1, 0);
    expect(b.take(0).allowed).toBe(true);
    expect(b.take(0).allowed).toBe(true);
    const blocked = b.take(0);
    expect(blocked.allowed).toBe(false);
    expect(blocked.remaining).toBe(0);
    expect(blocked.retryAfterMs).toBe(1000); // 1 token / 1 per sec
  });

  it("refills over time, capped at capacity", () => {
    const b = new TokenBucket(2, 1, 0);
    b.take(0);
    b.take(0); // empty
    expect(b.take(1000).allowed).toBe(true); // 1s -> 1 token refilled
    // long gap refills but never exceeds capacity
    expect(b.take(100_000).remaining).toBe(1); // capacity 2, took 1
  });
});

describe("RateLimiter", () => {
  it("keys buckets independently and uses injected clock", () => {
    let t = 0;
    const rl = new RateLimiter(1, 1, () => t);
    expect(rl.check("a").allowed).toBe(true);
    expect(rl.check("a").allowed).toBe(false); // a exhausted
    expect(rl.check("b").allowed).toBe(true); // b independent
    t = 1000;
    expect(rl.check("a").allowed).toBe(true); // refilled after 1s
  });

  it("defaults to a global key", () => {
    const rl = new RateLimiter(1, 1, () => 0);
    expect(rl.check().allowed).toBe(true);
    expect(rl.check().allowed).toBe(false);
  });
});

describe("originAllowed", () => {
  it("permits a missing origin (server-side client)", () => {
    expect(originAllowed(null, ["http://localhost:4321"])).toBe(true);
    expect(originAllowed("  ", ["http://localhost:4321"])).toBe(true);
  });
  it("permits an allowlisted origin and rejects others", () => {
    expect(originAllowed("http://localhost:4321", ["http://localhost:4321"])).toBe(true);
    expect(originAllowed("https://evil.example", ["http://localhost:4321"])).toBe(false);
  });
});

describe("allowedOrigins", () => {
  const saved = { url: process.env.DIE_FIRMA_DASHBOARD_URL, port: process.env.PORT };
  afterEach(() => {
    process.env.DIE_FIRMA_DASHBOARD_URL = saved.url;
    process.env.PORT = saved.port;
    if (saved.url === undefined) delete process.env.DIE_FIRMA_DASHBOARD_URL;
    if (saved.port === undefined) delete process.env.PORT;
  });

  it("derives origins from the dashboard URL + localhost", () => {
    process.env.DIE_FIRMA_DASHBOARD_URL = "http://127.0.0.1:4321/";
    process.env.PORT = "4321";
    const origins = allowedOrigins();
    expect(origins).toContain("http://127.0.0.1:4321");
    expect(origins).toContain("http://localhost:4321");
  });

  it("ignores a malformed dashboard URL", () => {
    process.env.DIE_FIRMA_DASHBOARD_URL = "::not a url::";
    delete process.env.PORT;
    const origins = allowedOrigins();
    expect(origins).toContain("http://localhost:4321"); // default port fallback
  });

  it("works with no dashboard URL set", () => {
    delete process.env.DIE_FIRMA_DASHBOARD_URL;
    process.env.PORT = "5000";
    expect(allowedOrigins()).toContain("http://127.0.0.1:5000");
  });
});

describe("numEnv", () => {
  const saved = process.env.DF_TEST_NUM;
  afterEach(() => {
    if (saved === undefined) delete process.env.DF_TEST_NUM;
    else process.env.DF_TEST_NUM = saved;
  });
  it("reads a number, falling back when unset or non-finite", () => {
    delete process.env.DF_TEST_NUM;
    expect(numEnv("DF_TEST_NUM", 42)).toBe(42);
    process.env.DF_TEST_NUM = "7";
    expect(numEnv("DF_TEST_NUM", 42)).toBe(7);
    process.env.DF_TEST_NUM = "nope";
    expect(numEnv("DF_TEST_NUM", 42)).toBe(42);
  });
});
