// Client for the multi-turn agent chat (/agent-chat). Owns the SSE parsing and
// the citation labelling so the ChatPanel stays a thin view. The agent runs as
// Claude Code on the user's cloud computer, so tool names are the harness's
// (Read, Grep, Bash, …) rather than bespoke API tools.

import { API_BASE, apiFetch, getAuthToken } from "@/lib/api";
import { getScopeUserId, SCOPE_HEADER } from "@/lib/scope-store";

// The two streaming calls below build their own headers (apiFetch can't stream),
// so they repeat api.ts's scope stamping: an agent chat started inside a
// workspace must read and write that workspace's knowledge base, not the
// personal one.
function scopeHeader(): Record<string, string> {
  const scopeUserId = getScopeUserId();
  return scopeUserId ? { [SCOPE_HEADER]: scopeUserId } : {};
}

export type Citation = {
  id: string;
  tool: string;
  label: string;
  // Direct link target: an external URL (WebFetch) or an app route (search,
  // page reads). VFS reads carry vfsPath instead and resolve to their app
  // route at click time via /vfs/resolve.
  href?: string;
  vfsPath?: string;
};
export type CitationTarget = Pick<Citation, "label" | "href" | "vfsPath">;
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
// edits are work, not grounding — they stay out of the strip. Reads of Stash
// content and web pages also carry a link target, so a citation is one click
// from the material it names; sprite-local reads (Read/Grep of ~/work
// scratch) have no app-side object and stay plain labels.
export function citationFor(
  name: string,
  args: Record<string, unknown> | undefined,
): CitationTarget | null {
  const a = args ?? {};
  if (name === "Read" && typeof a.file_path === "string") {
    return { label: basename(a.file_path) };
  }
  if ((name === "Grep" || name === "Glob") && typeof a.pattern === "string") {
    return { label: `search "${a.pattern.slice(0, 40)}"` };
  }
  if (name === "WebSearch" && typeof a.query === "string") {
    return { label: `web "${a.query.slice(0, 40)}"` };
  }
  if (name === "WebFetch" && typeof a.url === "string") {
    return { label: host(a.url), href: a.url };
  }
  if (name === "Task" && typeof a.description === "string") {
    return { label: `agent: ${a.description.slice(0, 40)}` };
  }
  if (name === "Bash" && typeof a.command === "string" && a.command.startsWith("stash ")) {
    return { label: a.command.slice(0, 48), ...stashCommandTarget(a.command) };
  }
  return null;
}

// Where a `stash` CLI read points in the app: a search opens /search with the
// same query, `stash read <page id>` opens the page, and a VFS cat carries
// its path for click-time resolution.
function stashCommandTarget(command: string): Omit<CitationTarget, "label"> {
  const search = command.match(/^stash search\s+"([^"]+)"/);
  if (search) return { href: `/search?q=${encodeURIComponent(search[1])}` };
  const read = command.match(/^stash read\s+([0-9a-f][0-9a-f-]{34}[0-9a-f])/);
  if (read) return { href: `/p/${read[1]}` };
  const cat = command.match(/\bcat\s+'([^']+)'/);
  if (cat) return { vfsPath: cat[1] };
  return {};
}

type StoredMessage = {
  role: ChatRole | "tool";
  content: string;
  tool_name?: string;
  metadata?: Record<string, unknown>;
};

/** Rebuild citationFor's args shape from a stored tool event's metadata
 *  ({command} for Bash, {file_path} for file tools, {args_preview} JSON for
 *  the rest). */
function argsFromMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  if (typeof metadata.args_preview === "string") {
    try {
      return JSON.parse(metadata.args_preview) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
  return metadata;
}

export async function getAgentChat(sessionId: string): Promise<ChatMessage[]> {
  const data = await apiFetch<{ messages: StoredMessage[] }>(
    `/api/v1/me/agent-chat/${encodeURIComponent(sessionId)}`,
  );
  // Fold stored tool rows into the citations of the assistant message that
  // follows them — the same shape the live stream builds turn by turn.
  const messages: ChatMessage[] = [];
  let pending: Citation[] = [];
  for (const [i, m] of data.messages.entries()) {
    if (m.role === "tool") {
      const target = citationFor(m.tool_name ?? "tool", argsFromMetadata(m.metadata ?? {}));
      if (target) pending.push({ id: `stored-${i}`, tool: m.tool_name ?? "tool", ...target });
      continue;
    }
    if (m.role === "assistant") {
      messages.push({ role: m.role, content: m.content, citations: pending });
      pending = [];
    } else {
      messages.push({ role: m.role, content: m.content });
    }
  }
  return messages;
}

/** Whether a turn is still running server-side for this session. Turns are
 *  detached from the stream, so one can outlive the panel that started it. */
export async function agentTurnRunning(sessionId: string): Promise<boolean> {
  const data = await apiFetch<{ running: boolean }>(
    `/api/v1/me/agent-chat/${encodeURIComponent(sessionId)}/status`,
  );
  return data.running;
}

type StreamHandlers = {
  onSession?: (sessionId: string) => void;
  onStatus?: (stage: string) => void;
  onText?: (delta: string) => void;
  onTool?: (citation: Citation) => void;
  onToolError?: (id: string) => void;
  onError?: (message: string) => void;
};

// Read an SSE agent stream and dispatch its events. Shared by chat turns and
// on-demand scheduled runs — both speak the same {session,status,text,tool,
// tool_result,error} contract.
async function consumeAgentStream(res: Response, handlers: StreamHandlers): Promise<void> {
  if (!res.ok || !res.body) {
    // Surface the server's own message (e.g. the Pro-upgrade prompt on 402).
    const detail = await res
      .json()
      .then((b) => b?.detail as string | undefined)
      .catch(() => undefined);
    throw new Error(detail || `Agent run failed: ${res.status}`);
  }

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
        handlers.onSession?.(evt.session_id);
      } else if (evt.type === "status" && typeof evt.stage === "string") {
        handlers.onStatus?.(evt.stage);
      } else if (evt.type === "text" && typeof evt.delta === "string") {
        handlers.onText?.(evt.delta);
      } else if (evt.type === "tool") {
        const target = citationFor(
          evt.name as string,
          evt.args as Record<string, unknown> | undefined,
        );
        if (target) {
          handlers.onTool?.({
            id: String(evt.id ?? target.label),
            tool: evt.name as string,
            ...target,
          });
        }
      } else if (evt.type === "tool_result" && evt.ok === false) {
        handlers.onToolError?.(String(evt.id));
      } else if (evt.type === "error" && typeof evt.message === "string") {
        handlers.onError?.(evt.message);
      }
    }
  }
}

// POST a message and dispatch streamed events. Resolves when the stream ends.
export async function streamAgentChat(
  opts: {
    sessionId: string | null;
    message: string;
    agentId?: string | null;
    signal?: AbortSignal;
  } & StreamHandlers,
): Promise<void> {
  const token = await getAuthToken();
  const res = await fetch(`${API_BASE}/api/v1/me/agent-chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...scopeHeader(),
    },
    body: JSON.stringify({
      message: opts.message,
      session_id: opts.sessionId,
      agent_id: opts.agentId ?? null,
    }),
    signal: opts.signal,
  });
  await consumeAgentStream(res, opts);
}

// Trigger a scheduled agent (e.g. the Memory curator) on demand and stream the
// run live. The server builds the prompt, so no message is sent.
export async function streamAgentRun(
  opts: { agentId: string; signal?: AbortSignal } & StreamHandlers,
): Promise<void> {
  const token = await getAuthToken();
  const res = await fetch(`${API_BASE}/api/v1/me/agent-chat/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...scopeHeader(),
    },
    body: JSON.stringify({ agent_id: opts.agentId }),
    signal: opts.signal,
  });
  await consumeAgentStream(res, opts);
}
