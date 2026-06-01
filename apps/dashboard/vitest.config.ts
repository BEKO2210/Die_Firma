import { getViteConfig } from "astro/config";

// Coverage gate on the logic-critical core (claude.md §4 / prompt §5):
// ingest validation + projection + secret check are held at 100%; the
// read-query helpers at a high floor. Wrapped in getViteConfig so the a11y
// test can import + render real .astro pages through Astro's Vite plugins.
export default getViteConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: [
        "src/lib/validate.ts",
        "src/lib/project.ts",
        "src/lib/secrets.ts",
        "src/lib/queries.ts",
      ],
      thresholds: {
        "src/lib/validate.ts": { statements: 100, branches: 100, functions: 100, lines: 100 },
        "src/lib/project.ts": { statements: 100, branches: 100, functions: 100, lines: 100 },
        "src/lib/secrets.ts": { statements: 100, branches: 100, functions: 100, lines: 100 },
        "src/lib/queries.ts": { statements: 95, branches: 90, functions: 100, lines: 95 },
      },
    },
  },
});
