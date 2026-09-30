import type { RmTraceSpan } from "@/lib/types";

export interface SpanRow {
  span: RmTraceSpan;
  depth: number;
  startMs: number;
  durationMs: number;
  hasChildren: boolean;
}

export function layoutSpans(spans: RmTraceSpan[], collapsed: ReadonlySet<string>) {
  if (spans.length === 0) return { rows: [], durationMs: 0 };
  const ordered = [...spans].sort((a, b) => {
    const difference = BigInt(a.start_ns) - BigInt(b.start_ns);
    return difference < 0 ? -1 : difference > 0 ? 1 : a.id.localeCompare(b.id);
  });
  const origin = BigInt(ordered[0].start_ns);
  const end = spans.reduce((latest, span) => BigInt(span.end_ns) > latest ? BigInt(span.end_ns) : latest, origin);
  const ids = new Set(spans.map((span) => span.id));
  const children = new Map<string | null, RmTraceSpan[]>();
  for (const span of ordered) {
    const parent = span.parent_id !== null && ids.has(span.parent_id) ? span.parent_id : null;
    const siblings = children.get(parent);
    if (siblings) siblings.push(span);
    else children.set(parent, [span]);
  }
  const rows: SpanRow[] = [];
  function visit(parent: string | null, depth: number) {
    for (const span of children.get(parent) ?? []) {
      rows.push({ span, depth, startMs: Number(BigInt(span.start_ns) - origin) / 1e6,
        durationMs: Number(BigInt(span.end_ns) - BigInt(span.start_ns)) / 1e6,
        hasChildren: children.has(span.id) });
      if (!collapsed.has(span.id)) visit(span.id, depth + 1);
    }
  }
  visit(null, 0);
  return { rows, durationMs: Number(end - origin) / 1e6 };
}

export function spanDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(1)} μs`;
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}
