// Design from Priyadarshan's trace viewer (projects/trace_viewer)
import type { RmStep } from "@/lib/types";

/**
 * What the timeline renders. A tool call and its result are two steps (each
 * rated and commented on separately) but read as one row, the way the trace
 * viewer pairs a tool_use with its tool_result.
 */
export type TraceRow =
  | { kind: "system"; key: string; step: RmStep }
  | { kind: "prompt"; key: string; step: RmStep; turn: number }
  | { kind: "assistant"; key: string; step: RmStep }
  | { kind: "tool"; key: string; call: RmStep | null; result: RmStep | null };

export type ToolFamily = "shell" | "read" | "edit" | "write" | "search" | "web" | "agent" | "ask" | "task" | "skill" | "mcp" | "browser" | "other";

export function isThinking(step: RmStep): boolean {
  return Boolean(step.metadata?.thinking);
}

export function buildRows(steps: RmStep[]): TraceRow[] {
  const rows: TraceRow[] = [];
  const pairedResults = new Set<string>();
  let turn = 0;

  steps.forEach((step, i) => {
    if (pairedResults.has(step.id)) return;

    if (step.role === "system") {
      rows.push({ kind: "system", key: step.id, step });
      return;
    }
    if (step.role === "user") {
      turn += 1;
      rows.push({ kind: "prompt", key: step.id, step, turn });
      return;
    }
    if (step.role === "tool") {
      rows.push({ kind: "tool", key: step.id, call: null, result: step });
      return;
    }
    if (step.tool_name === null) {
      rows.push({ kind: "assistant", key: step.id, step });
      return;
    }
    const result = steps.slice(i + 1).find((s) => s.role === "tool" && s.tool_call_id !== null && s.tool_call_id === step.tool_call_id);
    if (result) pairedResults.add(result.id);
    rows.push({ kind: "tool", key: step.id, call: step, result: result ?? null });
  });
  return rows;
}

/** Every step a row shows, in document order. */
export function rowSteps(row: TraceRow): RmStep[] {
  if (row.kind !== "tool") return [row.step];
  return [row.call, row.result].filter((s): s is RmStep => s !== null);
}

const FAMILY_BY_NAME: Record<string, ToolFamily> = {
  bash: "shell",
  shell: "shell",
  exec_command: "shell",
  run_command: "shell",
  read: "read",
  read_file: "read",
  edit: "edit",
  multiedit: "edit",
  apply_patch: "edit",
  write: "write",
  write_file: "write",
  grep: "search",
  glob: "search",
  search: "search",
  webfetch: "web",
  websearch: "web",
  web_search: "web",
  web_fetch: "web",
  fetch: "web",
  agent: "agent",
  task: "agent",
  askuserquestion: "ask",
  ask_user: "ask",
  todowrite: "task",
  update_plan: "task",
  skill: "skill",
};

export function toolFamily(name: string | null): ToolFamily {
  if (name === null) return "other";
  const n = name.toLowerCase();
  if (n.startsWith("mcp__")) return /browser|chrome|computer|playwright/.test(n) ? "browser" : "mcp";
  if (/browser|computer|screenshot|navigate/.test(n)) return "browser";
  return FAMILY_BY_NAME[n] ?? "other";
}

export function toolLabel(name: string | null): string {
  if (name === null) return "Tool";
  if (name.startsWith("mcp__")) {
    const parts = name.split("__").filter(Boolean);
    return `${parts[1] ?? "mcp"}, ${parts.slice(2).join(" ") || "tool"}`;
  }
  return name.replace(/[_-]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

// Fields that best say what a call did, in the order the one-line summary prefers them.
const SUMMARY_KEYS = ["command", "cmd", "file_path", "path", "pattern", "query", "q", "url", "description", "prompt"];

/** One-line mono summary of a tool call's input, like the trace viewer's tool rows. */
export function toolSummary(input: Record<string, unknown> | null): string {
  if (input === null) return "";
  for (const key of SUMMARY_KEYS) {
    const value = input[key];
    if (typeof value === "string" && value !== "") return firstLine(value);
  }
  const entries = Object.entries(input);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join("  ");
}

export function firstLine(text: string, max = 200): string {
  const line = text.split("\n").find((l) => l.trim() !== "") ?? "";
  return line.length > max ? `${line.slice(0, max)}…` : line.trim();
}

export function looksLikeError(text: string): boolean {
  return /^(error|traceback|script failed|command failed|exit code [1-9])/i.test(text.trim()) || /"error"\s*:/.test(text);
}
