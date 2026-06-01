// The dashboard process is the ONLY owner of the SQLite DB (prompt §1/§7).
// Python never opens it; it speaks HTTP to /api/ingest. WAL + single writer.

import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";
// Embed schema at build time so it survives bundling (no runtime file lookup).
import schemaSql from "./schema.sql?raw";

let instance: Database.Database | null = null;

function resolveDbPath(): string {
  const fromEnv = process.env.DIE_FIRMA_DB_PATH;
  if (fromEnv && fromEnv.trim() !== "") return path.resolve(fromEnv);
  return path.resolve(process.cwd(), "state", "dashboard.db");
}

/** Open (once) the read-model DB, applying schema + WAL pragmas. */
export function getDb(): Database.Database {
  if (instance !== null) return instance;
  const dbPath = resolveDbPath();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
  db.exec(schemaSql);
  instance = db;
  return db;
}

/** Test/script helper: build a fresh DB (in-memory by default) with schema. */
export function createDb(file = ":memory:"): Database.Database {
  const db = new Database(file);
  db.pragma("foreign_keys = ON");
  db.exec(schemaSql);
  return db;
}
