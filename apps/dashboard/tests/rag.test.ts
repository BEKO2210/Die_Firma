import { describe, expect, it } from "vitest";
import { condenseContext, contextSystemPrompt, expandQuery } from "../src/lib/rag.ts";
import type { Retrieved } from "../src/lib/rag.ts";

describe("query expansion", () => {
  it("appends unique extra terms, drops dupes (case-insensitive)", () => {
    expect(expandQuery("login bug", ["Login", "auth"])).toBe("login bug auth");
  });

  it("ignores blanks and caps length", () => {
    expect(expandQuery("  a  ", ["", "  "])).toBe("a");
    expect(expandQuery("x".repeat(500)).length).toBe(400);
  });
});

describe("context condensing", () => {
  const hits: Retrieved[] = [
    { file: "a.md", text: "A".repeat(100), score: 0.9 },
    { file: "b.md", text: "B".repeat(100), score: 0.5 },
  ];

  it("keeps whole chunks under budget", () => {
    const ctx = condenseContext(hits, 10_000);
    expect(ctx).toContain("### Datei: a.md");
    expect(ctx).toContain("### Datei: b.md");
  });

  it("truncates with an ellipsis when over budget", () => {
    const ctx = condenseContext(hits, 60);
    expect(ctx).toContain("### Datei: a.md");
    expect(ctx).toContain("…");
    // budget too small for the second block
    expect(ctx).not.toContain("### Datei: b.md");
  });
});

describe("contextSystemPrompt", () => {
  it("returns null with no hits", () => {
    expect(contextSystemPrompt([])).toBeNull();
  });

  it("embeds the condensed context", () => {
    const sys = contextSystemPrompt([{ file: "x.md", text: "hello", score: 1 }]);
    expect(sys).toContain("## Kontext aus outbox/");
    expect(sys).toContain("hello");
  });
});
