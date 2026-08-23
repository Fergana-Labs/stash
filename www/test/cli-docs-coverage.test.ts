/**
 * Coverage gate for the www CLI reference page (www/app/docs/cli/page.tsx).
 *
 * The registry guardrail (cli-docs-registry.test.ts) proves every CommandRef
 * on the page names a command that still exists in cli/main.py. This test is
 * the other direction — it proves the commands STAS-111's audit found
 * present-but-undocumented are actually documented, and it keeps the two
 * stale-description fixes in place: the marketing mock transcript
 * (www/app/docs/page.tsx) no longer demonstrates the removed
 * `stash sessions query`, and the CLI page no longer describes
 * `stash disconnect` as sign-out while leaving `stash logout` undocumented.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const PAGE = resolve(process.cwd(), "app/docs/cli/page.tsx");
const MARKETING = resolve(process.cwd(), "app/docs/page.tsx");

/** The 26 commands STAS-111's audit verified present in cli/main.py but undocumented. */
const INVENTORY = [
  "stash upgrade",
  "stash share",
  "stash export",
  "stash read",
  "stash changes",
  "stash verify-email",
  "stash welcome",
  "stash status",
  "stash logout",
  "stash download",
  "stash agent list",
  "stash agent chat",
  "stash agent run",
  "stash agent status",
  "stash agent watch",
  "stash agent stop",
  "stash trash list",
  "stash files edit-folder",
  "stash files edit-file",
  "stash files download",
  "stash skills add",
  "stash skills update",
  "stash skills unfollow",
  "stash sessions import",
  "stash tools list",
  "stash prompts agent-guidance",
] as const;

describe("cli-docs-coverage", () => {
  it("documents every inventory command as a CommandRef on the CLI page", () => {
    const page = readFileSync(PAGE, "utf8");
    const missing = INVENTORY.filter((cmd) => !page.includes(`command="${cmd}"`));
    expect(
      missing,
      `inventory commands missing a CommandRef on the CLI page: ${missing.join(", ")}`,
    ).toEqual([]);
  });

  it("the marketing mock transcript no longer shows the removed stash sessions query", () => {
    const page = readFileSync(MARKETING, "utf8");
    expect(
      page.includes("stash sessions query"),
      "mock transcript still demonstrates removed 'stash sessions query'",
    ).toBe(false);
    expect(page.includes("--since today"), "mock transcript still shows '--since today'").toBe(false);
  });

  it("the CLI page no longer describes stash disconnect as sign-out, and documents stash logout", () => {
    const page = readFileSync(PAGE, "utf8");
    expect(
      page.includes("clear all stored credentials"),
      "old stash disconnect sign-out drift text is still on the page",
    ).toBe(false);
    expect(page.includes('command="stash logout"'), "missing stash logout ref").toBe(true);
  });
});
