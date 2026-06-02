// Pluggable vector-store backend for RAG (review §9). The default is a tiny
// in-process cosine store (zero deps, fine for the outbox corpus). The
// VectorStore interface is the seam where a real vector DB (Qdrant, Chroma, …)
// can be dropped in for large corpora — implement add()/search() against the
// backend and swap it into rag.ts.

import { cosine } from "./ollama.ts";

export interface ScoredItem<T> {
  item: T;
  score: number;
}

export interface VectorStore<T> {
  /** Index one vector with its payload. */
  add(vector: number[], item: T): void;
  /** Top-k items by cosine similarity to `query`, filtered by `minScore`. */
  search(query: number[], k: number, minScore?: number): ScoredItem<T>[];
  /** Number of indexed vectors. */
  readonly size: number;
}

/** In-process exact cosine store. Deterministic; ties keep insertion order. */
export class InMemoryVectorStore<T> implements VectorStore<T> {
  private vectors: number[][] = [];
  private items: T[] = [];

  get size(): number {
    return this.items.length;
  }

  add(vector: number[], item: T): void {
    this.vectors.push(vector);
    this.items.push(item);
  }

  /** Convenience: bulk-load (vector, item) pairs. */
  addAll(entries: { vector: number[]; item: T }[]): void {
    for (const e of entries) this.add(e.vector, e.item);
  }

  search(query: number[], k: number, minScore = 0): ScoredItem<T>[] {
    const scored = this.items.map((item, i) => ({
      item,
      score: cosine(query, this.vectors[i]!),
    }));
    return scored
      .filter((s) => s.score > minScore)
      .sort((a, b) => b.score - a.score)
      .slice(0, Math.max(0, k));
  }
}
