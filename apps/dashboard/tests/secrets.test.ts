import { afterEach, describe, expect, it } from "vitest";
import { checkToken, getIngestToken, tokenFromRequest, tokenMatches } from "../src/lib/secrets.ts";

const GOOD = "Xk7_3sdf92kfjs03ksdf-aiwe9382"; // long, mixed classes, no placeholder

describe("checkToken — hardening", () => {
  it("rejects missing / empty", () => {
    expect(checkToken(undefined).reason).toBe("missing");
    expect(checkToken("   ").reason).toBe("missing");
  });
  it("rejects too short", () => {
    expect(checkToken("Ab1-xy").reason).toMatch(/too short/);
  });
  it("rejects known placeholders (case-insensitive)", () => {
    expect(checkToken("THIS-IS-A-CHANGEME-TOKEN-123456").reason).toMatch(/placeholder/);
    expect(checkToken("please-replace-this-value-now-00").reason).toMatch(/placeholder/);
  });
  it("rejects insufficient character variety", () => {
    expect(checkToken("aaaaaaaaaaaaaaaaaaaaaaaaaaaa").reason).toMatch(/character variety/);
  });
  it("accepts a strong token", () => {
    expect(checkToken(GOOD)).toEqual({ ok: true });
  });
});

describe("getIngestToken (env-driven)", () => {
  afterEach(() => {
    delete process.env.DIE_FIRMA_INGEST_TOKEN;
  });
  it("returns null for a bad token", () => {
    process.env.DIE_FIRMA_INGEST_TOKEN = "changeme";
    expect(getIngestToken()).toBeNull();
  });
  it("returns the trimmed token when valid", () => {
    process.env.DIE_FIRMA_INGEST_TOKEN = ` ${GOOD} `;
    expect(getIngestToken()).toBe(GOOD);
  });
});

describe("tokenMatches", () => {
  it("compares in constant time, handles null + length mismatch", () => {
    expect(tokenMatches(null, GOOD)).toBe(false);
    expect(tokenMatches("short", GOOD)).toBe(false);
    expect(tokenMatches(GOOD, GOOD)).toBe(true);
    expect(tokenMatches(GOOD.replace(/.$/, "Z"), GOOD)).toBe(false);
  });
});

describe("tokenFromRequest", () => {
  const req = (headers: Record<string, string>) => new Request("http://127.0.0.1/api/ingest", { headers });
  it("reads X-Die-Firma-Token", () => {
    expect(tokenFromRequest(req({ "x-die-firma-token": " abc " }))).toBe("abc");
  });
  it("reads Authorization: Bearer", () => {
    expect(tokenFromRequest(req({ authorization: "Bearer xyz" }))).toBe("xyz");
  });
  it("returns null when absent / non-bearer", () => {
    expect(tokenFromRequest(req({}))).toBeNull();
    expect(tokenFromRequest(req({ authorization: "Basic zzz" }))).toBeNull();
    expect(tokenFromRequest(req({ "x-die-firma-token": "  " }))).toBeNull();
  });
});
