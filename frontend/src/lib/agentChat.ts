// Client for the multi-turn agent chat (/agent-chat). Owns the SSE parsing and
// the citation labelling so the ChatPanel stays a thin view. The agent runs as
// Claude Code on the user's cloud computer, so tool names are the harness's
// (Read, Grep, Bash, …) rather than bespoke API tools.

import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";

export type Citation = { id: string; tool: string; label: string };
export type ChatRole = "user" | "assistant";
export type ChatMessage = { role: ChatRole; content: string; citations?: Citation[] };

function basename(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url.slice(0, 40);
  }
}

// The "Grounded on" strip shows the reads that grounded the answer: file and
// Stash reads, searches, and web lookups. Plain shell commands and file
// edits are work, not grounding — they stay out of the strip.
export function citationFor(
  name: string,
  args: Record<string, unknown> | undefined,
): string | null {
  const a = args ?? {};
  if (name === "Read" && typeof a.file_path === "string") return basename(a.file_path);
  if ((name === "Grep" || name === "Glob") && typeof a.pattern === "string") {
    return `search "${a.pattern.slice(0, 40)}"`;
  }
  if (name === "WebSearch" && typeof a.query === "string") {
    return `web "${a.query.slice(0, 40)}"`;
  }
  if (name === "WebFetch" && typeof a.url === "string") return host(a.url);
  if (name === "Task" && typeof a.description === "string") {
    return `agent: ${a.description.slice(0, 40)}`;
  }
  if (name === "Bash" && typeof a.command === "string" && a.command.startsWith("stash ")) {
    return a.command.slice(0, 48);
  }
  return null;
}

export async function getAgentChat(sessionId: string): Promise<ChatMessage[]> {
  const data = await apiFetch<{ messages: { role: ChatRole; content: string }[] }>(
    `/api/v1/me/agent-chat/${encodeURIComponent(sessionId)}`,
  );
  return data.messages.map((m) => ({ role: m.role, content: m.content }));
}

type StreamHandlers = {
  onSession?: (sessionId: string) => void;
  onStatus?: (stage: string) => void;
  onText?: (delta: string) => void;
  onTool?: (citation: Citation) => void;
  onToolError?: (id: string) => void;
  onError?: (message: string) => void;
};

// POST a message and dispatch streamed events. Resolves when the stream ends.
export async function streamAgentChat(
  opts: {
    sessionId: string | null;
    message: string;
    signal?: AbortSignal;
  } & StreamHandlers,
): Promise<void> {
  const token = await getAuthToken();
  const res = await fetch(`${API_BASE}/api/v1/me/agent-chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message: opts.message, session_id: opts.sessionId }),
    signal: opts.signal,
  });
  if (!res.ok || !res.body) throw new Error(`Chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const raw of chunks) {
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      let evt: Record<string, unknown>;
      try {
        evt = JSON.parse(payload);
      } catch {
        continue; // partial frame — resume next read
      }
      if (evt.type === "session" && typeof evt.session_id === "string") {
        opts.onSession?.(evt.session_id);
      } else if (evt.type === "status" && typeof evt.stage === "string") {
        opts.onStatus?.(evt.stage);
      } else if (evt.type === "text" && typeof evt.delta === "string") {
        opts.onText?.(evt.delta);
      } else if (evt.type === "tool") {
        const label = citationFor(
          evt.name as string,
          evt.args as Record<string, unknown> | undefined,
        );
        if (label) {
          opts.onTool?.({ id: String(evt.id ?? label), tool: evt.name as string, label });
        }
      } else if (evt.type === "tool_result" && evt.ok === false) {
        opts.onToolError?.(String(evt.id));
      } else if (evt.type === "error" && typeof evt.message === "string") {
        opts.onError?.(evt.message);
      }
    }
  }
}
