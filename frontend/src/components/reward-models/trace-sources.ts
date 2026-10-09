import type { RmTraceSummary } from "@/lib/types";

export function traceSourceId(trace: RmTraceSummary): string {
  return trace.source_id ?? trace.agent ?? trace.source_format ?? "unknown";
}

export function traceSourceKey(trace: RmTraceSummary): string {
  return `${trace.source_owner_id ?? ""}/${traceSourceId(trace)}`;
}

export function traceSourceName(trace: RmTraceSummary): string {
  const id = traceSourceId(trace);
  return trace.source_name ?? ({ codex: "Codex", claude_code: "Claude Code", otel: "OpenTelemetry", stash: "Stash" } as Record<string, string>)[id] ?? id;
}

export type TraceFilters = { source: string; from: string; through: string };

/** Dates match the local calendar dates shown in the Imported column. */
export function matchesTraceFilters(trace: RmTraceSummary, filters: TraceFilters): boolean {
  if (filters.source !== "all" && traceSourceKey(trace) !== filters.source) return false;
  if (!filters.from && !filters.through) return true;
  const date = new Date(trace.created_at);
  if (Number.isNaN(date.getTime())) return false;
  const localDay = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return (!filters.from || localDay >= filters.from) && (!filters.through || localDay <= filters.through);
}
