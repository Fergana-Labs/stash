/**
 * Docs-to-CLI consistency gate for www/app/docs/cli/page.tsx.
 *
 * Parses the Typer registry from cli/main.py (read-only ground truth) and
 * asserts that every CommandRef on the public CLI reference page names a
 * command that still exists. This is the automated guard against the
 * stale-docs bug class fixed in STAS-108 (docs/architecture.html) and
 * STAS-111 (this page): a removed command must fail this test the moment
 * the page keeps documenting it.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const CLI_MAIN = resolve(process.cwd(), "../cli/main.py");
const PAGE = resolve(process.cwd(), "app/docs/cli/page.tsx");

interface Group {
  members: Set<string>;
  /** True when the group registers a @<var>.callback, so `stash <group>` runs bare. */
  bare: boolean;
}

interface Registry {
  topLevel: Set<string>;
  groups: Map<string, Group>;
}

const ADD_TYPER = /^app\.add_typer\(\s*(\w+)\s*,\s*name="([a-z][a-z-]*)"/;
const NAMED_COMMAND = /^@(\w+)\.command\(\s*"([a-z][a-z-]*)"\s*[,)]/;
const UNNAMED_COMMAND = /^@(\w+)\.command\(\s*\)\s*$/;
const GROUP_CALLBACK = /^@(\w+)\.callback\(/;
const DEF = /^def (\w+)\(/;

function parseRegistry(source: string): Registry {
  const lines = source.split("\n");
  const groupVars = new Map<string, string>();
  const groups = new Map<string, Group>();
  const topLevel = new Set<string>();

  // Pass 1: group registrations (var -> name) and bare-form callbacks.
  for (const line of lines) {
    const typer = line.match(ADD_TYPER);
    if (typer) {
      const [_, variable, name] = typer;
      groupVars.set(variable, name);
      groups.set(name, { members: new Set<string>(), bare: false });
      continue;
    }
    const callback = line.match(GROUP_CALLBACK);
    if (callback) {
      const [_, variable] = callback;
      const name = groupVars.get(variable);
      if (name) groups.get(name)!.bare = true;
    }
  }

  // Pass 2: command decorators, named or unnamed (name from the following def).
  for (let i = 0; i < lines.length; i++) {
    const named = lines[i].match(NAMED_COMMAND);
    if (named) {
      const [_, variable, name] = named;
      const group = groupVars.get(variable);
      if (group) groups.get(group)!.members.add(name);
      else if (variable === "app") topLevel.add(name);
      else
        throw new Error(
          `Unexpected command owner @${variable}.command("${name}") at line ${i + 1}`,
        );
      continue;
    }
    const unnamed = lines[i].match(UNNAMED_COMMAND);
    if (unnamed) {
      const [_, variable] = unnamed;
      const def = lines[i + 1]?.match(DEF);
      if (!def) {
        throw new Error(`Unnamed @${variable}.command() at line ${i + 1} is not followed by a def`);
      }
      const group = groupVars.get(variable);
      if (group) groups.get(group)!.members.add(def[1]);
      else if (variable === "app") topLevel.add(def[1]);
      else throw new Error(`Unexpected command owner @${variable}.command() at line ${i + 1}`);
    }
  }

  return { topLevel, groups };
}

/** A single token must be a top-level command or a bare-capable group; a two-token
 * command must be `group sub` with sub a member of that group. */
function resolves(registry: Registry, command: string): boolean {
  const parts = command.slice("stash ".length).split(" ");
  if (parts.length === 1) {
    if (registry.topLevel.has(parts[0])) return true;
    const group = registry.groups.get(parts[0]);
    return group ? group.bare : false;
  }
  if (parts.length === 2) {
    return registry.groups.get(parts[0])?.members.has(parts[1]) ?? false;
  }
  return false;
}

describe("cli-docs-registry", () => {
  it("registry sentinels match the current CLI surface", () => {
    const registry = parseRegistry(readFileSync(CLI_MAIN, "utf8"));
    for (const name of ["connect", "ls", "setup", "sql", "start", "stop"]) {
      expect(registry.topLevel.has(name), `expected top-level command "${name}"`).toBe(true);
    }
    for (const name of ["disable", "enable", "install"]) {
      expect(registry.topLevel.has(name), `removed command "${name}" reappeared`).toBe(false);
    }
    expect([...registry.groups.get("files")!.members].sort()).toEqual([
      "add-page",
      "create-folder",
      "download",
      "edit-file",
      "edit-folder",
      "edit-page",
      "read-page",
      "text",
    ]);
    expect([...registry.groups.get("sessions")!.members].sort()).toEqual([
      "agents",
      "assign",
      "delete-folder",
      "folders",
      "import",
      "new-folder",
      "push",
      "rename-folder",
    ]);
    expect([...registry.groups.get("sources")!.members].sort()).toEqual(["add", "rm", "sync"]);
    expect([...registry.groups.get("tables")!.members].sort()).toEqual([
      "add-column",
      "count",
      "create",
      "delete",
      "delete-column",
      "delete-row",
      "export",
      "import",
      "insert",
      "update",
      "update-row",
    ]);
    expect(registry.groups.get("workspace")!.members.has("list")).toBe(true);
    expect(registry.groups.get("workspace")!.members.has("switch")).toBe(true);
    expect(registry.groups.get("memory")!.bare).toBe(true);
  });

  it("every CommandRef on the page names a real command", () => {
    const registry = parseRegistry(readFileSync(CLI_MAIN, "utf8"));
    const page = readFileSync(PAGE, "utf8");
    const refs = [...page.matchAll(/command="(stash [^"]+)"/g)].map((m) => m[1]);
    expect(refs.length).toBeGreaterThan(0);
    const stale = [...new Set(refs.filter((ref) => !resolves(registry, ref)))];
    expect(stale, `stale CommandRefs (not in cli/main.py): ${stale.join(", ")}`).toEqual([]);
  });

  it("documents the current streaming surface instead of the removed one", () => {
    const page = readFileSync(PAGE, "utf8");
    for (const removed of [
      'command="stash install"',
      'command="stash enable"',
      'command="stash disable"',
    ]) {
      expect(page.includes(removed), `page still documents removed ${removed}`).toBe(false);
    }
    const start = page.indexOf("<H2>Streaming & hooks</H2>");
    expect(start, "Streaming & hooks section missing from the page").toBeGreaterThan(-1);
    const end = page.indexOf("<H2>", start + 1);
    const section = page.slice(start, end === -1 ? undefined : end);
    expect(section.includes('command="stash start"'), "missing stash start in Streaming & hooks").toBe(true);
    expect(section.includes('command="stash stop"'), "missing stash stop in Streaming & hooks").toBe(true);
  });

  it("no prose on the page points at the removed stash sources ls", () => {
    const page = readFileSync(PAGE, "utf8");
    expect(
      page.includes("stash sources ls"),
      'page still references removed "stash sources ls"',
    ).toBe(false);
  });
});
