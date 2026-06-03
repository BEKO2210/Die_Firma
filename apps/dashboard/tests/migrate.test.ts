import { describe, expect, it } from "vitest";
import Database from "better-sqlite3";
import { MIGRATIONS, runMigrations, userVersion } from "../src/lib/migrate.ts";

function rawDb() {
  const db = new Database(":memory:");
  db.exec("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, task_id TEXT, ts TEXT)");
  return db;
}

describe("schema migrations", () => {
  it("fresh DB starts at user_version 0", () => {
    expect(userVersion(rawDb())).toBe(0);
  });

  it("applies all migrations in order and bumps user_version", () => {
    const db = rawDb();
    const final = runMigrations(db);
    const max = Math.max(...MIGRATIONS.map((m) => m.version));
    expect(final).toBe(max);
    expect(userVersion(db)).toBe(max);
    // the v2 index migration actually created the index
    const idx = db
      .prepare("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_events_ts'")
      .get();
    expect(idx).toBeTruthy();
  });

  it("is idempotent — re-running applies nothing", () => {
    const db = rawDb();
    runMigrations(db);
    const before = userVersion(db);
    expect(runMigrations(db)).toBe(before); // no-op second time
  });

  it("only applies migrations newer than the current version", () => {
    const db = rawDb();
    const calls: number[] = [];
    const migrations = [
      { version: 1, name: "a", sql: "" },
      {
        version: 2,
        name: "b",
        sql: "CREATE TABLE t2 (x)",
      },
      { version: 3, name: "c", sql: "CREATE TABLE t3 (x)" },
    ];
    db.pragma("user_version = 2"); // pretend we're already at v2
    runMigrations(db, migrations);
    void calls;
    // t2 should NOT exist (skipped), t3 should (applied).
    const t2 = db.prepare("SELECT name FROM sqlite_master WHERE name='t2'").get();
    const t3 = db.prepare("SELECT name FROM sqlite_master WHERE name='t3'").get();
    expect(t2).toBeFalsy();
    expect(t3).toBeTruthy();
    expect(userVersion(db)).toBe(3);
  });
});
