/**
 * Octopus plugin for opencode.
 *
 * Thin TS shim: each opencode event handler serializes its input and pipes it
 * into the matching Python hook script via stdin. All real work happens in
 * plugins/shared/ (Python), reused from every other agent's plugin.
 *
 * Bus events (session.*, message.*, file.*, etc.) are delivered through the
 * single `event` hook, NOT as keyed properties. Only the explicit allow-list
 * in opencode's `Hooks` interface (chat.message, tool.execute.*, etc.) is
 * dispatched by key.
 *
 * Install: reference this file from your opencode `plugin` config. See README.
 */

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCRIPTS = join(PLUGIN_ROOT, "scripts");
const PYTHON = process.env.OCTOPUS_PYTHON ?? "python3";

// opencode never emits a clean session-end signal. After this much idle time
// inside a live opencode process, treat the session as ended and fire
// on_session_end.py. Reset on every activity event (chat, tool, session.idle).
const IDLE_END_MS = 10 * 60 * 1000;

let idleTimer: ReturnType<typeof setTimeout> | null = null;
let activeSessionId = "";

function scheduleIdleEnd(sessionId: string): void {
  if (idleTimer) clearTimeout(idleTimer);
  if (!sessionId) return;
  activeSessionId = sessionId;
  idleTimer = setTimeout(() => {
    runHook("on_session_end.py", { session_id: sessionId });
    activeSessionId = "";
    idleTimer = null;
  }, IDLE_END_MS);
}

function cancelIdleEnd(): void {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = null;
  activeSessionId = "";
}

function runHook(script: string, payload: unknown): void {
  // Fire-and-forget. We never want a flaky Octopus backend to stall opencode.
  // detached + unref so the child belongs to its own process group and gets
  // reaped independently — otherwise zombies accumulate over long sessions.
  try {
    const child = spawn(PYTHON, [join(SCRIPTS, script)], {
      stdio: ["pipe", "ignore", "ignore"],
      detached: true,
    });
    child.on("error", () => { /* python missing / crash — swallow */ });
    child.stdin?.write(JSON.stringify(payload));
    child.stdin?.end();
    child.unref();
  } catch {
    // spawn failed synchronously — swallow
  }
}

function extractText(parts: any[] | undefined): string {
  if (!Array.isArray(parts)) return "";
  return parts
    .filter((p) => p?.type === "text")
    .map((p) => p?.text ?? "")
    .join("\n");
}

export const OctopusPlugin = async ({
  project,
  worktree,
}: {
  project?: { worktree?: string };
  worktree?: string;
}) => {
  const cwd = worktree ?? project?.worktree ?? "";

  return {
    // Keyed hook: fires once per user message.
    "chat.message": async (
      _input: unknown,
      output: { message: any; parts: any[] },
    ) => {
      const text = extractText(output?.parts) || output?.message?.content || "";
      const sid = output?.message?.sessionID ?? "";
      runHook("on_prompt.py", { session_id: sid, prompt: text, cwd });
      scheduleIdleEnd(sid);
    },

    // Keyed hook: fires once per tool call, after execution.
    // Real signature: (input, output) where
    //   input = {tool, sessionID, callID, args}
    //   output = {title, output, metadata}
    "tool.execute.after": async (
      input: { tool: string; sessionID: string; callID: string; args: any },
      output: { title: string; output: string; metadata: any },
    ) => {
      runHook("on_tool_use.py", {
        session_id: input?.sessionID ?? "",
        tool_name: input?.tool ?? "",
        tool_input: input?.args ?? {},
        tool_response: {
          title: output?.title,
          output: output?.output,
          metadata: output?.metadata,
        },
        cwd,
      });
      scheduleIdleEnd(input?.sessionID ?? "");
    },

    // Generic bus-event dispatcher. Every session.* / message.* / file.* event
    // lands here — we switch on event.type.
    event: async ({ event }: { event: { type: string; properties?: any } }) => {
      switch (event?.type) {
        case "session.created": {
          const info = event.properties?.info;
          const sid = info?.id ?? "";
          runHook("on_session_start.py", { session_id: sid, cwd });
          scheduleIdleEnd(sid);
          break;
        }
        case "session.deleted": {
          const info = event.properties?.info;
          runHook("on_session_end.py", { session_id: info?.id ?? "" });
          cancelIdleEnd();
          break;
        }
        case "session.idle": {
          // session.idle fires every turn completion — refresh the idle timer
          // so the 10-min countdown only fires after real inactivity.
          scheduleIdleEnd(activeSessionId);
          break;
        }
      }
    },
  };
};

export default OctopusPlugin;
