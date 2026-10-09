import { traceScore, traceCredits } from "./trace-metrics";
import type { RmTraceSummary } from "@/lib/types";
import { traceSourceName } from "./trace-sources";

export type TraceSortKey = "title" | "source" | "steps" | "comments" | "reward" | "credit" | "minCredit" | "maxCredit" | "imported";
export type TraceSortDirection = "ascending" | "descending";

export function sortTraces(traces: RmTraceSummary[], key: TraceSortKey, direction: TraceSortDirection, source: "automatic" | "learned" = "learned"): RmTraceSummary[] {
  const sign = direction === "ascending" ? 1 : -1;
  return [...traces].sort((a, b) => {
    // Unscored traces belong after scored traces in either direction.
    if (["credit", "minCredit", "maxCredit", "reward"].includes(key)) {
      const value = (trace: RmTraceSummary) => key === "reward"
        ? source === "automatic" ? traceScore(trace) : trace.latest_score?.score
        : (source === "automatic" ? traceCredits(trace) : trace.action_credit)?.[key === "minCredit" ? "min" : key === "maxCredit" ? "max" : "mean"];
      const av = value(a), bv = value(b);
      if (av == null && bv == null) return a.id.localeCompare(b.id);
      if (av == null) return 1;
      if (bv == null) return -1;
      return sign * (av - bv) || a.id.localeCompare(b.id);
    }
    let difference = 0;
    switch (key) {
      case "title": difference = a.title.localeCompare(b.title); break;
      case "source": difference = traceSourceName(a).localeCompare(traceSourceName(b)); break;
      case "steps": difference = a.step_count - b.step_count; break;
      case "comments": difference = a.comment_count - b.comment_count; break;
      case "imported": difference = Date.parse(a.created_at) - Date.parse(b.created_at); break;
    }
    return sign * difference || a.id.localeCompare(b.id);
  });
}

/** `?selected=id1,id2` on the Traces tab preselects traces, e.g. from a model card's "Trained on N traces". */
export const SELECTED_PARAM = "selected";

export function searchTraces(traces: RmTraceSummary[], query: string): RmTraceSummary[] {
  const needle = query.trim().toLowerCase();
  return traces.filter((trace) => trace.title.toLowerCase().includes(needle));
}

/** Sets every id between two rows (inclusive, either direction) to `value`. This is shift-click. */
export function selectRange(
  orderedIds: string[],
  selected: Set<string>,
  from: number,
  to: number,
  value: boolean,
): Set<string> {
  const next = new Set(selected);
  const [low, high] = from < to ? [from, to] : [to, from];
  for (const id of orderedIds.slice(low, high + 1)) {
    if (value) next.add(id);
    else next.delete(id);
  }
  return next;
}

/** Header checkbox: select every visible row, or clear them all if they already are. Rows hidden by the filter keep their state. */
export function toggleAllVisible(visibleIds: string[], selected: Set<string>): Set<string> {
  const allSelected = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const next = new Set(selected);
  for (const id of visibleIds) {
    if (allSelected) next.delete(id);
    else next.add(id);
  }
  return next;
}

export interface SelectionSummary {
  count: number;
}

export function summarizeSelection(traces: RmTraceSummary[], selected: Set<string>): SelectionSummary {
  return { count: traces.filter((trace) => selected.has(trace.id)).length };
}
