/**
 * Octopus plugin for opencode.
 *
 * Thin TS shim: each opencode event handler serializes its input and pipes it
 * into the matching Python hook script via stdin. All real work happens in
 * plugins/shared/ (Python), reused from every other agent's plugin.
 *
 * Install: reference this file from your opencode plugins config. See README.
 */

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCRIPTS = join(PLUGIN_ROOT, "scripts");

function runHook(script: string, payload: unknown): void {
  // Fire-and-forget. We never want a flaky Octopus backend to stall opencode.
  const child = spawn("python3", [join(SCRIPTS, script)], {
    stdio: ["pipe", "ignore", "ignore"],
    detached: false,
  });
  child.on("error", () => { /* python missing / crash — swallow */ });
  try {
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  } catch {
    // spawn failed synchronously (e.g. ENOENT on python3) — swallow
  }
}

export const OctopusPlugin = async ({ project }: { project: { worktree: string } }) => ({
  "session.created": async (input: any) => {
    runHook("on_session_start.py", {
      session_id: input.session?.id ?? input.id ?? "",
      cwd: project?.worktree ?? "",
    });
  },

  "message.updated": async (input: any) => {
    const msg = input.message ?? input;
    if (msg?.role !== "user") return;
    const text =
      typeof msg.content === "string"
        ? msg.content
        : (msg.content?.map?.((p: any) => p.text ?? "").join("\n") ?? "");
    runHook("on_prompt.py", {
      session_id: input.session_id ?? msg.session_id ?? "",
      prompt: text,
      cwd: project?.worktree ?? "",
    });
  },

  "tool.execute.after": async (input: any) => {
    runHook("on_tool_use.py", {
      session_id: input.session_id ?? "",
      tool_name: input.tool ?? input.name ?? "",
      tool_input: input.args ?? input.input ?? {},
      tool_response: input.output ?? input.result ?? null,
      cwd: project?.worktree ?? "",
    });
  },

  "session.idle": async (input: any) => {
    runHook("on_stop.py", {
      session_id: input.session_id ?? input.id ?? "",
      last_assistant_message: input.last_message ?? "",
      cwd: project?.worktree ?? "",
    });
  },

  "session.deleted": async (input: any) => {
    runHook("on_session_end.py", {
      session_id: input.session_id ?? input.id ?? "",
    });
  },
});

export default OctopusPlugin;
