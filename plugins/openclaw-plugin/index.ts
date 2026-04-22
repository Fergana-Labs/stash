/**
 * Stash extension for Openclaw.
 *
 * Subscribes to Openclaw's plugin-hook system (`session_start`,
 * `before_message_write`, `session_end`). Unlike the channel-centric
 * `message:received` / `message:sent` internal hooks, these fire for every
 * turn regardless of transport — telegram, webchat, Control UI direct chat,
 * subagents — because they're emitted by the canonical agent runtime.
 *
 * All HTTP work runs in-process. Auth + workspace come from
 * `~/.stash/config.json` (the CLI's config, populated by `stash connect`).
 * Failed posts are queued to `<data>/event_queue.jsonl` and retried on the
 * next successful post, matching the stashai Python client's behavior.
 */

import { existsSync, mkdirSync, readFileSync, appendFileSync, readFileSync as read, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

import { definePluginEntry } from "openclaw/plugin-sdk/core";

type StashConfig = {
  base_url?: string;
  api_key?: string;
  username?: string;
};

type StashManifest = {
  workspace_id?: string;
};

type EventBody = {
  agent_name: string;
  event_type: "session_start" | "user_message" | "assistant_message" | "session_end";
  content: string;
  session_id?: string;
  metadata?: Record<string, unknown>;
};

const CONFIG_PATH = join(homedir(), ".stash", "config.json");
const DATA_DIR = join(homedir(), ".stash", "plugins", "openclaw");
const QUEUE_PATH = join(DATA_DIR, "event_queue.jsonl");
const QUEUE_MAX = 1000;
const DRAIN_BATCH = 50;

function readConfig(): StashConfig {
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf8")) as StashConfig;
  } catch {
    return {};
  }
}

function findManifest(): StashManifest | null {
  let dir = process.cwd();
  while (true) {
    const candidate = join(dir, ".stash", "stash.json");
    if (existsSync(candidate)) {
      try { return JSON.parse(readFileSync(candidate, "utf8")) as StashManifest; }
      catch { return null; }
    }
    const parent = join(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function eventsPath(workspaceId: string): string {
  return workspaceId
    ? `/api/v1/workspaces/${workspaceId}/memory/events`
    : `/api/v1/memory/events`;
}

function extractText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const block of content) {
    if (block && typeof block === "object" && "type" in block) {
      const b = block as { type: string; text?: string };
      if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
    }
  }
  return parts.join("\n");
}

// Openclaw prepends `Sender (untrusted metadata):\n\`\`\`json\n{...}\n\`\`\`\n\n<text>`
// to user messages. Strip the wrapper so Stash stores the literal user turn.
function stripSenderWrapper(text: string): string {
  if (!text.startsWith("Sender (untrusted metadata):")) return text;
  const jsonStart = text.indexOf("```json");
  if (jsonStart === -1) return text;
  const jsonEnd = text.indexOf("```", jsonStart + 7);
  if (jsonEnd === -1) return text;
  return text.slice(jsonEnd + 3).trimStart();
}

function ensureDataDir(): void {
  try { mkdirSync(DATA_DIR, { recursive: true }); } catch { /* ignore */ }
}

function enqueue(path: string, body: EventBody): void {
  try {
    ensureDataDir();
    appendFileSync(QUEUE_PATH, JSON.stringify({ path, body, ts: Date.now() / 1000 }) + "\n");
    trimQueue();
  } catch { /* ignore */ }
}

function trimQueue(): void {
  try {
    const lines = read(QUEUE_PATH, "utf8").split("\n").filter(Boolean);
    if (lines.length <= QUEUE_MAX) return;
    const keep = lines.slice(-QUEUE_MAX);
    writeFileSync(QUEUE_PATH, keep.join("\n") + "\n");
  } catch { /* ignore */ }
}

async function postRaw(base: string, apiKey: string, path: string, body: unknown): Promise<boolean> {
  try {
    const res = await fetch(base.replace(/\/$/, "") + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function drainQueue(base: string, apiKey: string): Promise<void> {
  if (!existsSync(QUEUE_PATH)) return;
  let lines: string[];
  try { lines = read(QUEUE_PATH, "utf8").split("\n").filter(Boolean); } catch { return; }
  if (lines.length === 0) return;

  const remaining: string[] = [];
  let sent = 0;
  for (const line of lines) {
    if (sent >= DRAIN_BATCH) { remaining.push(line); continue; }
    try {
      const entry = JSON.parse(line) as { path: string; body: EventBody };
      const ok = await postRaw(base, apiKey, entry.path, entry.body);
      if (ok) { sent += 1; } else { remaining.push(line); sent = DRAIN_BATCH; }
    } catch { remaining.push(line); }
  }
  try { writeFileSync(QUEUE_PATH, remaining.length ? remaining.join("\n") + "\n" : ""); }
  catch { /* ignore */ }
}

async function pushEvent(body: EventBody): Promise<void> {
  const cfg = readConfig();
  const manifest = findManifest();
  const base = cfg.base_url ?? "https://api.stash.ac";
  const apiKey = cfg.api_key ?? "";
  const workspaceId = manifest?.workspace_id ?? "";
  if (!apiKey) return;

  const fullBody: EventBody = {
    ...body,
    agent_name: cfg.username ?? "openclaw",
    metadata: { ...(body.metadata ?? {}), client: "openclaw" },
  };
  const path = eventsPath(workspaceId);

  const ok = await postRaw(base, apiKey, path, fullBody);
  if (!ok) { enqueue(path, fullBody); return; }
  await drainQueue(base, apiKey);
}

// Fire-and-forget: a slow Stash backend must never stall Openclaw.
function send(body: EventBody): void {
  pushEvent(body).catch(() => { /* swallow */ });
}

export default definePluginEntry({
  id: "stash",
  name: "Stash",
  description: "Stream Openclaw sessions to a Stash workspace.",
  register(api) {
    api.on("session_start", (event, ctx) => {
      send({
        agent_name: "",
        event_type: "session_start",
        content: "",
        session_id: event.sessionKey ?? event.sessionId ?? ctx.sessionKey,
        metadata: { cwd: "" },
      });
    });

    api.on("before_message_write", (event, ctx) => {
      const role = (event.message as { role?: string })?.role;
      const content = (event.message as { content?: unknown })?.content;
      const text = extractText(content);
      if (!text) return;

      if (role === "user") {
        send({
          agent_name: "",
          event_type: "user_message",
          content: stripSenderWrapper(text),
          session_id: event.sessionKey ?? ctx.sessionKey,
        });
        return;
      }
      if (role === "assistant") {
        send({
          agent_name: "",
          event_type: "assistant_message",
          content: text,
          session_id: event.sessionKey ?? ctx.sessionKey,
        });
        return;
      }
      // role === "toolResult" — skip. Coding-agent plugins cover tool history.
    });

    api.on("session_end", (event, ctx) => {
      send({
        agent_name: "",
        event_type: "session_end",
        content: "",
        session_id: event.sessionKey ?? event.sessionId ?? ctx.sessionKey,
      });
    });
  },
});
