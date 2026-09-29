import type { RmTraceSummary } from "@/lib/types";

export type TraceFilter = "all" | "annotated" | "unannotated";

/** `?selected=id1,id2` on the Traces tab preselects traces, e.g. from a model card's "Trained on N traces". */
export const SELECTED_PARAM = "selected";

// Training fails below this many preference pairs.
export const MIN_PAIRS = 2;

function isAnnotated(t: RmTraceSummary): boolean {
  return t.positive_count + t.negative_count + t.comment_count + t.label_error_count > 0;
}

export function hasLabels(t: RmTraceSummary): boolean {
  return t.positive_count + t.negative_count > 0;
}

export function filterTraces(traces: RmTraceSummary[], filter: TraceFilter, query: string): RmTraceSummary[] {
  const needle = query.trim().toLowerCase();
  return traces.filter((t) => {
    if (filter === "annotated" && !isAnnotated(t)) return false;
    if (filter === "unannotated" && isAnnotated(t)) return false;
    return needle === "" || t.title.toLowerCase().includes(needle);
  });
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
  positive: number;
  negative: number;
}

export function summarizeSelection(traces: RmTraceSummary[], selected: Set<string>): SelectionSummary {
  const picked = traces.filter((t) => selected.has(t.id));
  return {
    count: picked.length,
    positive: picked.reduce((sum, t) => sum + t.positive_count, 0),
    negative: picked.reduce((sum, t) => sum + t.negative_count, 0),
  };
}

/**
 * Pairs are chosen × rejected targets within a granularity, and collapsing
 * ratings per target only lowers that, so positive × negative is an upper
 * bound. Below MIN_PAIRS the selection certainly can't train; above it the
 * server has the final word.
 */
export function tooFewPairs(summary: SelectionSummary): boolean {
  return summary.positive * summary.negative < MIN_PAIRS;
}
