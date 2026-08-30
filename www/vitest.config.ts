import { defineConfig } from "vitest/config";

// Scope Vitest to the TypeScript suites only. The globals-css guard is a
// node:test file — Vitest cannot collect a suite it did not register, so it
// would report "No test suite found" and fail the run. That guard runs on its
// own: `node --test test/globals-css.test.mjs` (docs/testing.md, Landing page).
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
  },
});
