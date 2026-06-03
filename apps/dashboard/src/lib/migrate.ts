// Lightweight SQLite schema migrations via PRAGMA user_version (review #6).
// No ORM: numbered migrations are applied in order, each in a transaction that
// also bumps user_version, so a failed migration leaves the version untouched
// and is safely retried. The base tables come from schema.sql (idempotent
// CREATE IF NOT EXISTS); migrations evolve it from there.

import type DatabaseType from "better-sqlite3";

type DB = DatabaseType.Database;

export interface Migration {
  version: number;
  name: string;
  sql: string;
}

// Ordered migrations. v1 is the baseline (tables created by schema.sql); later
// versions add indexes/columns. Append new entries with the next integer.
export const MIGRATIONS: Migration[] = [
  { version: 1, name: "baseline", sql: "" },
  {
    version: 2,
    name: "event read indexes",
    sql: `
      CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
      CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id);
    `,
  },
];

/** Current schema version stored in the DB (0 on a fresh database). */
export function userVersion(db: DB): number {
  return Number(db.pragma("user_version", { simple: true }));
}

/**
 * Apply every migration newer than the DB's current ``user_version`` in order,
 * each atomically with its version bump. Returns the resulting version.
 */
export function runMigrations(db: DB, migrations: Migration[] = MIGRATIONS): number {
  let current = userVersion(db);
  for (const m of [...migrations].sort((a, b) => a.version - b.version)) {
    if (m.version <= current) continue;
    db.transaction(() => {
      const sql = m.sql.trim();
      if (sql) db.exec(sql);
      // user_version only accepts an integer literal, not a bound parameter.
      db.pragma(`user_version = ${m.version}`);
    })();
    current = m.version;
  }
  return current;
}
