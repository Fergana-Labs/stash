/**
 * Stash hook for Openclaw.
 *
 * Registered against Openclaw's `command` and `message` internal events.
 * Branches on event.type + event.action and pipes a flat JSON payload into
 * the matching Python hook script. All Stash API work happens in
 * plugins/shared/ (Python), reused from every other agent's plugin.
 *
 * Upstream types: openclaw/openclaw src/hooks/internal-hook-types.ts
 * Event catalog:  openclaw/openclaw src/hooks/internal-hooks.ts
 */

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { HookHandler, InternalHookEvent } from "@openclaw/sdk";

const PLUGIN_ROOT = dirname(fileURLToPath(import.meta.url));
const SCRIPTS = join(PLUGIN_ROOT, "scripts");
const PYTHON = process.env.STASH_PYTHON ?? "python3";

function runHook(script: string, payload: unknown): void {
  // Fire-and-forget. A flaky Stash backend must never stall Openclaw's gateway.
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

function cwdOf(event: InternalHookEvent): string {
  const ctx = event.context as Record<string, unknown>;
  const wd = ctx?.workspaceDir;
  return typeof wd === "string" ? wd : "";
}

const stashHandler: HookHandler = async (event) => {
  if (event.type === "command" && event.action === "new") {
    runHook("on_session_start.py", {
      session_id: event.sessionKey,
      cwd: cwdOf(event),
    });
    return;
  }

  if (event.type === "command" && (event.action === "reset" || event.action === "stop")) {
    runHook("on_session_end.py", { session_id: event.sessionKey });
    return;
  }

  if (event.type === "message" && event.action === "received") {
    const ctx = event.context as { content?: string; channelId?: string };
    runHook("on_prompt.py", {
      session_id: event.sessionKey,
      prompt: ctx?.content ?? "",
      cwd: cwdOf(event),
      channel_id: ctx?.channelId ?? "",
    });
    return;
  }

  if (event.type === "message" && event.action === "sent") {
    const ctx = event.context as { content?: string; success?: boolean; channelId?: string };
    if (ctx?.success === false) return;
    runHook("on_stop.py", {
      session_id: event.sessionKey,
      last_assistant_message: ctx?.content ?? "",
      cwd: cwdOf(event),
      channel_id: ctx?.channelId ?? "",
    });
    return;
  }
};

export default stashHandler;
