// Pure helpers for the session trace view: turning transcript events into
// renderable turns, and summarizing tool calls for progressive disclosure.

import type { SessionEvent } from "@/lib/api";

export interface MessageTurn {
  id: string;
  who: "user" | "assistant" | "system";
  name: string;
  time?: string;
  dateKey?: string;
  dateLabel?: string;
  content: string;
  toolName?: string | null;
}

// Scheduled runs (the Memory curator and other scheduled agents) have no human
// turns: every "user" event in them is the server-built prompt for that run,
// so the viewer labels those as the system prompt they are.
export function isScheduledRunSession(sessionId: string): boolean {
  return /^agent-(curate|sched)-/.test(sessionId);
}

export function eventToTurn(
  ev: SessionEvent,
  sessionId: string,
  humanName: string | null
): MessageTurn {
  const createdAt = ev.created_at ? new Date(ev.created_at) : null;
  const who =
    ev.role === "user" && isScheduledRunSession(sessionId) ? "system" : ev.role;

  return {
    id: ev.id,
    who,
    name: speakerName(who, ev.agent_name, humanName),
    time: createdAt
      ? createdAt.toLocaleTimeString(undefined, {
          hour: "numeric",
          minute: "2-digit",
        })
      : undefined,
    dateKey: createdAt ? formatDateKey(createdAt) : undefined,
    dateLabel: createdAt ? formatSessionDate(createdAt) : undefined,
    content: ev.content,
    toolName: ev.tool_name,
  };
}

function speakerName(
  who: MessageTurn["who"],
  agentName: string,
  humanName: string | null
): string {
  if (who === "system") return "System prompt";
  if (who === "assistant") return agentName || "agent";
  return humanName || "user";
}

export interface ToolDisplay {
  // One-line excerpt for the collapsed tool row.
  summary: string;
  // Full content for the expanded view.
  body: string;
}

// Tool inputs arrive as the JSON repr of the tool call's arguments (or as a
// plain string for older events). Bash-style calls get their command shown as
// the code itself; everything else is pretty-printed JSON.
export function toolDisplay(content: string): ToolDisplay {
  const parsed = parseJsonObject(content);
  if (!parsed) return { summary: oneLine(content), body: content };

  if (typeof parsed.command === "string") {
    const summary =
      typeof parsed.description === "string" ? parsed.description : parsed.command;
    return { summary: oneLine(summary), body: parsed.command };
  }

  return {
    summary: oneLine(toolSummaryField(parsed) ?? content),
    body: JSON.stringify(parsed, null, 2),
  };
}

function parseJsonObject(content: string): Record<string, unknown> | null {
  if (!content.trimStart().startsWith("{")) return null;
  try {
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function toolSummaryField(input: Record<string, unknown>): string | null {
  for (const key of ["description", "file_path", "path", "query", "url"]) {
    if (typeof input[key] === "string") return input[key] as string;
  }
  return null;
}

const SUMMARY_MAX_CHARS = 120;

function oneLine(text: string): string {
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (collapsed.length <= SUMMARY_MAX_CHARS) return collapsed;
  return collapsed.slice(0, SUMMARY_MAX_CHARS) + "…";
}

export function formatDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatSessionDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
