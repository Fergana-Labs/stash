// Client for the multi-turn agent chat (/agent-chat). Owns the SSE parsing and
// the citation labelling so the ChatPanel stays a thin view.

import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";

export type Citation = { id: string; tool: string; label: string };
export type ChatRole = "user" | "assistant";
export type ChatMessage = { role: ChatRole; content: string; citations?: Citation[] };

// Tools whose calls are worth showing in the "Grounded on" strip.
export const READ_TOOLS = new Set([
  "read_page",
  "grep_pages",
  "read_file",
  "search_history",
  "search",
  "read_source",
  "list_source",
]);

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

export function describeToolCall(
  name: string,
  args: Record<string, unknown> | undefined,
): string {
  if (!args) return name;
  if (name === "read_page" && typeof args.page_id === "string") return `page ${shortId(args.page_id)}`;
  if (name === "read_file" && typeof args.file_id === "string") return `file ${shortId(args.file_id)}`;
  if (
    (name === "grep_pages" || name === "search_history" || name === "search") &&
    typeof args.query === "string"
  ) {
    return `search "${args.query.slice(0, 40)}"`;
  }
  if (name === "read_source" && typeof args.ref === "string") return `read ${args.ref.slice(0, 48)}`;
  if (name === "list_source" && typeof args.source === "string") {
    const path = typeof args.path === "string" && args.path ? `/${args.path}` : "";
    return `browse ${args.source}${path}`;
  }
  return name;
}

export async function getAgentChat(
  workspaceId: string,
  sessionId: string,
): Promise<ChatMessage[]> {
  const data = await apiFetch<{ messages: { role: ChatRole; content: string }[] }>(
    `/api/v1/workspaces/${workspaceId}/agent-chat/${encodeURIComponent(sessionId)}`,
  );
  return data.messages.map((m) => ({ role: m.role, content: m.content }));
}

type StreamHandlers = {
  onSession?: (sessionId: string) => void;
  onText?: (delta: string) => void;
  onTool?: (citation: Citation) => void;
  onToolError?: (id: string) => void;
  // The agent rendered/updated a generative-UI canvas; open it in the side panel.
  onCanvas?: (canvasId: string) => void;
};

// POST a message and dispatch streamed events. Resolves when the stream ends.
export async function streamAgentChat(
  opts: {
    workspaceId: string;
    sessionId: string | null;
    message: string;
    signal?: AbortSignal;
  } & StreamHandlers,
): Promise<void> {
  const token = await getAuthToken();
  const res = await fetch(`${API_BASE}/api/v1/workspaces/${opts.workspaceId}/agent-chat`, {
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
      } else if (evt.type === "text" && typeof evt.delta === "string") {
        opts.onText?.(evt.delta);
      } else if (evt.type === "tool" && READ_TOOLS.has(evt.name as string)) {
        const id = String(evt.id ?? describeToolCall(evt.name as string, evt.args as Record<string, unknown>));
        opts.onTool?.({
          id,
          tool: evt.name as string,
          label: describeToolCall(evt.name as string, evt.args as Record<string, unknown>),
        });
      } else if (evt.type === "tool_result" && evt.ok === false) {
        opts.onToolError?.(String(evt.id));
      } else if (evt.type === "canvas" && typeof evt.id === "string") {
        opts.onCanvas?.(evt.id);
      }
    }
  }
}
