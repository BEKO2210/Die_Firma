// Accessibility gate (claude.md §4 / prompt §5): render the real index page
// via Astro's container API (node env — the container compiles via esbuild,
// which cannot run under a jsdom global), then run axe-core inside a JSDOM
// window over the produced HTML.

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { JSDOM } from "jsdom";
import axe from "axe-core";

const dbPath = path.join(os.tmpdir(), `die-firma-a11y-${process.pid}.db`);

beforeAll(() => {
  process.env.DIE_FIRMA_DB_PATH = dbPath;
});
afterAll(() => {
  for (const suffix of ["", "-wal", "-shm"]) {
    fs.rmSync(dbPath + suffix, { force: true });
  }
});

describe("dashboard accessibility", () => {
  it("index page has no axe violations", async () => {
    const { experimental_AstroContainer: AstroContainer } = await import("astro/container");
    const { default: IndexPage } = await import("../src/pages/index.astro");
    const container = await AstroContainer.create();
    const html = await container.renderToString(IndexPage);

    // Strip the page's own client scripts so jsdom doesn't try to run them.
    const dom = new JSDOM(html, { runScripts: "outside-only" });
    const { window } = dom;

    // Inject the axe-core source into the window and run it there.
    window.eval(axe.source);
    const results = (await (window as unknown as {
      axe: { run: (ctx: Document, opts: unknown) => Promise<{ violations: { id: string; help: string }[] }> };
    }).axe.run(window.document, {
      // color-contrast needs real paint/layout, unavailable in jsdom.
      rules: { "color-contrast": { enabled: false } },
    }));

    const violations = results.violations.map((v) => `${v.id}: ${v.help}`);
    expect(violations).toEqual([]);
  });
});
