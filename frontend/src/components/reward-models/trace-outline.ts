import type { TraceRow } from "./trace-rows";
import { isThinking, rowSteps, toolFamily } from "./trace-rows";
import { readableExcerpt, rowHead } from "./trace-presentation";

export interface TraceGroup {
  key: string;
  rows: TraceRow[];
  children: TraceGroup[];
}

function group(rows: TraceRow[], keyPrefix = "group"): TraceGroup {
  return { key: `${keyPrefix}-${rows[0].key}`, rows, children: [] };
}

/** Recognizable changes in work can form subtasks without inventing size-based cuts. */
function activity(row: TraceRow): string | null {
  if (row.kind !== "tool") return null;
  const step = rowHead(row);
  const family = toolFamily(step.tool_name);
  if (family === "read" || family === "search") return "inspect";
  if (family === "edit" || family === "write") return "edit";
  const input = step.tool_input ?? {};
  if (typeof input.url === "string" && (family === "browser" || family === "web")) {
    try { return `site:${new URL(input.url).host}`; } catch { return null; }
  }
  // Native Codex wraps shell and patch calls in an exec envelope.
  const wrapped = typeof input.input === "string" ? input.input : typeof input.code === "string" ? input.code : "";
  if (/\btools\.apply_patch\s*\(/.test(wrapped)) return "edit";
  const command = typeof input.cmd === "string" ? input.cmd : typeof input.command === "string" ? input.command : wrapped.match(/\b(?:cmd|command)["']?\s*:\s*["']([^"'\n]*)/)?.[1] ?? "";
  if (/(?:^|[;&|]\s*)(?:\S*\/)?(?:vitest|pytest|jest|eslint|tsc|ruff|playwright)\b|\b(?:npm|pnpm|yarn) (?:run )?(?:test|lint|typecheck)\b|\bpython[\d.]* -m pytest\b/.test(command)) return "verify";
  if (/\bgit (?:commit|push)\b|\bgh pr (?:create|merge)\b/.test(command)) return "publish";
  if (/^(?:rg|cat|sed|ls|find)\b|^git (?:status|diff|log|show)\b/.test(command.trim())) return "inspect";
  return null;
}

function splitActivities(node: TraceGroup): TraceGroup {
  const runs: TraceRow[][] = [[]];
  let previous: string | null = null;
  for (const row of node.rows) {
    const next = activity(row);
    if (next && previous && next !== previous) runs.push([]);
    runs.at(-1)!.push(row);
    if (next) previous = next;
  }
  if (runs.length > 1) node.children = runs.map((rows) => group(rows, node.key));
  return node;
}

/** Requests contain recorded progress phases, which can contain distinct activities.
 * A continuous stretch of work stays together regardless of its length. */
function subdivide(node: TraceGroup): TraceGroup {
  const phases: TraceRow[][] = [[]];
  let hasWork = false;
  for (const row of node.rows) {
    const progress = row.kind === "assistant" && row.step.metadata?.phase === "commentary";
    if (progress && hasWork) { phases.push([]); hasWork = false; }
    phases.at(-1)!.push(row);
    if (row.kind === "tool" || (row.kind === "assistant" && !progress && !row.step.metadata?.thinking)) hasWork = true;
  }
  if (phases.length === 1) return splitActivities(node);
  node.children = phases.map((rows) => splitActivities(group(rows, node.key)));
  return node;
}

/** Recorded task labels and request boundaries determine the hierarchy; generated copy decorates it. */
export function buildTraceOutline(rows: TraceRow[]): TraceGroup[] {
  const tasks: TraceGroup[] = [];
  let taskId: string | null = null;
  let hasWork = false;
  for (const row of rows) {
    const step = rowHead(row);
    const label = step.metadata?.label as { task_id?: string; intent?: string } | undefined;
    const explicitNew = label?.task_id && label.task_id !== taskId;
    const continuation = /^(?:thanks?\b|thank you\b|ok(?:ay)?\b|yes\b|no\b|but\b|wait\b|why\b)/i.test(readableExcerpt(step.content));
    const newRequest = row.kind === "prompt" && (label?.intent ? label.intent === "new_request" : label?.task_id ? !!explicitNew : !continuation);
    if (!tasks.length || explicitNew || (newRequest && hasWork)) {
      tasks.push(group([row], "task"));
      hasWork = false;
    } else tasks.at(-1)!.rows.push(row);
    if (row.kind === "assistant" || row.kind === "tool") hasWork = true;
    if (label?.task_id) taskId = label.task_id;
  }
  return tasks.map(subdivide);
}

export function groupPath(groups: TraceGroup[], stepId: string): string[] {
  for (const node of groups) {
    if (!node.rows.some((row) => rowSteps(row).some((step) => step.id === stepId))) continue;
    return [node.key, ...groupPath(node.children, stepId)];
  }
  return [];
}

export function resolveGroupPath(groups: TraceGroup[], path: string[]): TraceGroup[] {
  const result: TraceGroup[] = [];
  for (const key of path) {
    const node = groups.find((item) => item.key === key);
    if (!node) break;
    result.push(node);
    groups = node.children;
  }
  return result;
}

/** One task is already the overview; keep it in the breadcrumb, not behind a card. */
export function traceExplorerLevel(groups: TraceGroup[], path: string[]) {
  let trail = resolveGroupPath(groups, path);
  if (!trail.length && groups.length === 1) trail = [groups[0]];
  const current = trail.at(-1);
  return {
    trail, current,
    children: current ? current.children : groups,
    canAscend: trail.length > (groups.length === 1 ? 1 : 0),
  };
}

/** Immediate, source-grounded copy while optional generated titles are loading. */
export function sectionFallbackTitle(node: TraceGroup): string {
  const progress = node.rows.find((row) => row.kind === "assistant" && row.step.metadata?.phase === "commentary" && row.step.content.trim());
  if (progress) return readableExcerpt(rowHead(progress).content, 70);
  const work = node.rows.map(activity).find(Boolean);
  if (work?.startsWith("site:")) return `Accessing ${work.slice(5)}`;
  const labels: Record<string, string> = { inspect: "Inspecting files and results", edit: "Editing code", verify: "Running checks", publish: "Publishing changes" };
  if (work && labels[work]) return labels[work];
  const firstWork = node.rows.findIndex((row) => row.kind === "assistant" || row.kind === "tool");
  const request = node.rows.slice(0, firstWork < 0 ? undefined : firstWork).findLast((row) => row.kind === "prompt");
  if (request) return readableExcerpt(rowHead(request).content, 70) || "User request";
  const response = node.rows.find((row) => row.kind === "assistant" && !isThinking(row.step) && row.step.content.trim());
  return response ? readableExcerpt(rowHead(response).content, 70) : node.rows.some((row) => row.kind === "tool") ? "Tool activity" : "Messages";
}
