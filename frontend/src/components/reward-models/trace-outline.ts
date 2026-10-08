import type { TraceRow } from "./trace-rows";
import { rowSteps, toolLabel, toolSummary } from "./trace-rows";
import { readableExcerpt, rowHead } from "./trace-presentation";

export interface TraceGroup {
  key: string;
  title: string;
  summary: string;
  rows: TraceRow[];
  children: TraceGroup[];
}

function describe(row: TraceRow): string {
  const step = rowHead(row);
  return row.kind === "tool" ? `${toolLabel(step.tool_name)}${toolSummary(step.tool_input) ? ` · ${toolSummary(step.tool_input)}` : ""}` : readableExcerpt(step.content, 180);
}

function group(rows: TraceRow[], title?: string, keyPrefix = "group"): TraceGroup {
  const lastAnswer = [...rows].reverse().find((row) => row.kind === "assistant" && !row.step.metadata?.thinking);
  const calls = rows.filter((row) => row.kind === "tool").length;
  return {
    key: `${keyPrefix}-${rows[0].key}`, rows, children: [],
    title: title || describe(rows[0]) || "Recorded work",
    summary: lastAnswer ? readableExcerpt(rowHead(lastAnswer).content, 240) : `${calls} tool ${calls === 1 ? "call" : "calls"} across ${rows.length} steps`,
  };
}

/** Bounded branching keeps long stretches of tool work navigable down to a row. */
function subdivide(node: TraceGroup): TraceGroup {
  if (node.rows.length <= 8) return node;
  const phases: TraceRow[][] = [];
  for (const row of node.rows) {
    if (!phases.length || (row.kind === "assistant" && row.step.metadata?.phase === "commentary" && phases.at(-1)!.length > 1)) phases.push([]);
    phases.at(-1)!.push(row);
  }
  if (phases.length <= 1) {
    phases.length = 0;
    const size = Math.ceil(node.rows.length / Math.min(6, Math.ceil(node.rows.length / 8)));
    for (let i = 0; i < node.rows.length; i += size) phases.push(node.rows.slice(i, i + size));
  }
  if (phases.length > 6) {
    const size = Math.ceil(phases.length / 6);
    node.children = Array.from({ length: Math.ceil(phases.length / size) }, (_, i) => subdivide(group(phases.slice(i * size, (i + 1) * size).flat(), undefined, node.key)));
  } else node.children = phases.map((rows) => subdivide(group(rows, undefined, node.key)));
  return node;
}

/** Prefer recorded task labels; otherwise use requests and recorded progress, without inventing summaries. */
export function buildTraceOutline(rows: TraceRow[]): TraceGroup[] {
  const tasks: TraceGroup[] = [];
  let taskId: string | null = null;
  for (const row of rows) {
    const step = rowHead(row);
    const label = step.metadata?.label as { task_id?: string; intent?: string } | undefined;
    const explicitNew = label?.task_id && label.task_id !== taskId;
    const continuation = /^(?:thanks?\b|thank you\b|ok(?:ay)?\b|yes\b|no\b|also\b|and\b|but\b|wait\b|why\b)/i.test(readableExcerpt(step.content));
    const newRequest = row.kind === "prompt" && (label?.intent ? label.intent === "new_request" : !continuation);
    if (!tasks.length || explicitNew || newRequest) {
      tasks.push(group([row], row.kind === "prompt" ? readableExcerpt(step.content, 150) : "Initial work", "task"));
    } else tasks.at(-1)!.rows.push(row);
    if (label?.task_id) taskId = label.task_id;
  }
  return tasks.map((task) => subdivide({ ...group(task.rows, task.title, "task"), key: task.key }));
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
