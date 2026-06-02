import { describe, expect, it } from "vitest";
import { InMemoryVectorStore } from "../src/lib/vectorstore.ts";

describe("InMemoryVectorStore", () => {
  it("ranks by cosine similarity and respects k", () => {
    const s = new InMemoryVectorStore<string>();
    s.addAll([
      { vector: [1, 0], item: "east" },
      { vector: [0, 1], item: "north" },
      { vector: [0.9, 0.1], item: "east-ish" },
    ]);
    expect(s.size).toBe(3);
    const top = s.search([1, 0], 2);
    expect(top.map((r) => r.item)).toEqual(["east", "east-ish"]);
    expect(top[0]!.score).toBeGreaterThan(top[1]!.score);
  });

  it("filters by minScore", () => {
    const s = new InMemoryVectorStore<string>();
    s.add([1, 0], "a");
    s.add([0, 1], "b"); // orthogonal -> score 0
    expect(s.search([1, 0], 5, 0.5).map((r) => r.item)).toEqual(["a"]);
  });

  it("k<=0 returns nothing", () => {
    const s = new InMemoryVectorStore<string>();
    s.add([1, 0], "a");
    expect(s.search([1, 0], 0)).toEqual([]);
  });
});
