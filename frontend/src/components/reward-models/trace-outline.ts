import type { TraceRow } from "./trace-rows";
import { rowSteps } from "./trace-rows";
import { readableExcerpt, rowHead } from "./trace-presentation";

export interface TraceGroup {
  key: string;
  rows: TraceRow[];
  children: TraceGroup[];
}

function group(rows: TraceRow[], keyPrefix = "group"): TraceGroup {
  return { key: `${keyPrefix}-${rows[0].key}`, rows, children: [] };
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
    const size = Math.ceil(node.rows.length / Math.min(4, Math.ceil(node.rows.length / 8)));
    for (let i = 0; i < node.rows.length; i += size) phases.push(node.rows.slice(i, i + size));
  }
  if (phases.length > 4) {
    const size = Math.ceil(phases.length / 4);
    node.children = Array.from({ length: Math.ceil(phases.length / size) }, (_, i) => subdivide(group(phases.slice(i * size, (i + 1) * size).flat(), node.key)));
  } else node.children = phases.map((rows) => subdivide(group(rows, node.key)));
  return node;
}

/** Group adjacent tasks without losing their boundaries; every zoom level has at most four choices. */
function boundLevel(nodes: TraceGroup[]): TraceGroup[] {
  if (nodes.length <= 4) return nodes;
  const size = Math.ceil(nodes.length / 4);
  return Array.from({ length: Math.ceil(nodes.length / size) }, (_, i) => {
    const children = boundLevel(nodes.slice(i * size, (i + 1) * size));
    return { ...group(children.flatMap((child) => child.rows), `overview-${nodes.length}`), children };
  });
}

/** Recorded task labels and request boundaries determine the hierarchy; generated copy decorates it. */
export function buildTraceOutline(rows: TraceRow[]): TraceGroup[] {
  const tasks: TraceGroup[] = [];
  let taskId: string | null = null;
  for (const row of rows) {
    const step = rowHead(row);
    const label = step.metadata?.label as { task_id?: string; intent?: string } | undefined;
    const explicitNew = label?.task_id && label.task_id !== taskId;
    const continuation = /^(?:thanks?\b|thank you\b|ok(?:ay)?\b|yes\b|no\b|but\b|wait\b|why\b)/i.test(readableExcerpt(step.content));
    const newRequest = row.kind === "prompt" && (label?.intent ? label.intent === "new_request" : label?.task_id ? !!explicitNew : !continuation);
    if (!tasks.length || explicitNew || newRequest) {
      tasks.push(group([row], "task"));
    } else tasks.at(-1)!.rows.push(row);
    if (label?.task_id) taskId = label.task_id;
  }
  return boundLevel(tasks.map(subdivide));
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
