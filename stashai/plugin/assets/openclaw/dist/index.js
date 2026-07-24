import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, appendFileSync, readFileSync as read, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { definePluginEntry } from "openclaw/plugin-sdk/core";
const CONFIG_PATH = join(homedir(), ".stash", "config.json");
const DATA_DIR = join(homedir(), ".stash", "plugins", "openclaw");
const QUEUE_PATH = join(DATA_DIR, "event_queue.jsonl");
const QUEUE_MAX = 1e3;
const DRAIN_BATCH = 50;
function readConfig() {
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf8"));
  } catch {
    return {};
  }
}
const EVENTS_PATH = "/api/v1/me/sessions/events";
function extractText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts = [];
  for (const block of content) {
    if (block && typeof block === "object" && "type" in block) {
      const b = block;
      if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
    }
  }
  return parts.join("\n");
}
function stripSenderWrapper(text) {
  if (!text.startsWith("Sender (untrusted metadata):")) return text;
  const jsonStart = text.indexOf("```json");
  if (jsonStart === -1) return text;
  const jsonEnd = text.indexOf("```", jsonStart + 7);
  if (jsonEnd === -1) return text;
  return text.slice(jsonEnd + 3).trimStart();
}
function ensureDataDir() {
  try {
    mkdirSync(DATA_DIR, { recursive: true });
  } catch {
  }
}
function enqueue(path, body) {
  try {
    ensureDataDir();
    appendFileSync(QUEUE_PATH, JSON.stringify({ path, body, ts: Date.now() / 1e3 }) + "\n");
    trimQueue();
  } catch {
  }
}
function trimQueue() {
  try {
    const lines = read(QUEUE_PATH, "utf8").split("\n").filter(Boolean);
    if (lines.length <= QUEUE_MAX) return;
    const keep = lines.slice(-QUEUE_MAX);
    writeFileSync(QUEUE_PATH, keep.join("\n") + "\n");
  } catch {
  }
}
async function postRaw(base, apiKey, path, body) {
  try {
    const res = await fetch(base.replace(/\/$/, "") + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(3e3)
    });
    return res.ok;
  } catch {
    return false;
  }
}
async function drainQueue(base, apiKey) {
  if (!existsSync(QUEUE_PATH)) return;
  let lines;
  try {
    lines = read(QUEUE_PATH, "utf8").split("\n").filter(Boolean);
  } catch {
    return;
  }
  if (lines.length === 0) return;
  const remaining = [];
  let sent = 0;
  for (const line of lines) {
    if (sent >= DRAIN_BATCH) {
      remaining.push(line);
      continue;
    }
    try {
      const entry = JSON.parse(line);
      const ok = await postRaw(base, apiKey, entry.path, entry.body);
      if (ok) {
        sent += 1;
      } else {
        remaining.push(line);
        sent = DRAIN_BATCH;
      }
    } catch {
      remaining.push(line);
    }
  }
  try {
    writeFileSync(QUEUE_PATH, remaining.length ? remaining.join("\n") + "\n" : "");
  } catch {
  }
}
async function pushEvent(body) {
  const cfg = readConfig();
  const base = cfg.base_url ?? "https://joinstash.ai";
  const apiKey = cfg.api_key ?? "";
  if (!apiKey) return;
  const fullBody = {
    ...body,
    agent_name: cfg.username ?? "openclaw",
    metadata: { ...body.metadata ?? {}, client: "openclaw" }
  };
  const path = EVENTS_PATH;
  const ok = await postRaw(base, apiKey, path, fullBody);
  if (!ok) {
    enqueue(path, fullBody);
    return;
  }
  await drainQueue(base, apiKey);
}
function send(body) {
  pushEvent(body).catch(() => {
  });
}
function runHook(event, payload) {
  try {
    const child = spawn("stash", ["hook", "run", "openclaw", event], {
      stdio: ["pipe", "ignore", "ignore"],
      detached: true
    });
    child.on("error", () => {
    });
    child.stdin?.write(JSON.stringify(payload));
    child.stdin?.end();
    child.unref();
  } catch {
  }
}
var index_default = definePluginEntry({
  id: "stash",
  name: "Stash",
  description: "Stream Openclaw sessions to your Stash.",
  register(api) {
    api.on("session_start", (event, ctx) => {
      const sessionId = event.sessionKey ?? event.sessionId ?? ctx.sessionKey;
      runHook("on_session_start", { session_id: sessionId, cwd: process.cwd() });
      send({
        agent_name: "",
        event_type: "session_start",
        content: "",
        session_id: sessionId,
        metadata: { cwd: process.cwd() }
      });
    });
    api.on("before_message_write", (event, ctx) => {
      const role = event.message?.role;
      const content = event.message?.content;
      const text = extractText(content);
      if (!text) return;
      if (role === "user") {
        send({
          agent_name: "",
          event_type: "user_message",
          content: stripSenderWrapper(text),
          session_id: event.sessionKey ?? ctx.sessionKey
        });
        return;
      }
      if (role === "assistant") {
        send({
          agent_name: "",
          event_type: "assistant_message",
          content: text,
          session_id: event.sessionKey ?? ctx.sessionKey
        });
        return;
      }
    });
    api.on("session_end", (event, ctx) => {
      const sessionId = event.sessionKey ?? event.sessionId ?? ctx.sessionKey;
      runHook("on_session_end", { session_id: sessionId, cwd: process.cwd() });
    });
  }
});
export {
  index_default as default
};
