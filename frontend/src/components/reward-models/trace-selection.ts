import type { RmTraceSummary } from "@/lib/types";

export type TraceSortKey = "title" | "steps" | "comments" | "reward" | "imported";
export type TraceSortDirection = "ascending" | "descending";

export function sortTraces(traces: RmTraceSummary[], key: TraceSortKey, direction: TraceSortDirection): RmTraceSummary[] {
  const sign = direction === "ascending" ? 1 : -1;
  return [...traces].sort((a, b) => {
    // Unscored traces belong after scored traces in either direction.
    if (key === "reward") {
      if (a.latest_score === null && b.latest_score === null) return a.id.localeCompare(b.id);
      if (a.latest_score === null) return 1;
      if (b.latest_score === null) return -1;
      return sign * (a.latest_score.score - b.latest_score.score) || a.id.localeCompare(b.id);
    }
    let difference: number;
    switch (key) {
      case "title": difference = a.title.localeCompare(b.title); break;
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
