// @ts-check
import { defineConfig } from "astro/config";
import node from "@astrojs/node";

// Standalone Node server (prompt §1: Astro + Node adapter, standalone).
// Bind strictly to loopback (claude.md §6 / prompt §7). Host/port come from
// env so production can override without code changes; defaults are loopback.
const host = process.env.DASHBOARD_HOST ?? "127.0.0.1";
const port = Number(process.env.DASHBOARD_PORT ?? "4321");

export default defineConfig({
  output: "server",
  adapter: node({ mode: "standalone" }),
  server: { host, port },
  // The dashboard is read-only UI + the single ingest writer; no telemetry,
  // no external assets.
  devToolbar: { enabled: false },
});
