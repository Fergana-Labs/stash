import { describe, expect, it } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import { filterTraces, selectRange, summarizeSelection, toggleAllVisible, tooFewPairs } from "./trace-selection";

function trace(id: string, title: string, positive: number, negative: number, comments = 0): RmTraceSummary {
  return {
    id,
    external_id: null,
    title,
    source_format: "otel",
    step_count: 3,
    positive_count: positive,
    negative_count: negative,
    comment_count: comments,
    label_error_count: 0,
    latest_score: null,
    created_at: "2026-09-28T00:00:00Z",
  };
}

const traces = [
  trace("a", "Refund request", 2, 0),
  trace("b", "Shipping delay", 0, 0),
  trace("c", "Refund denied", 0, 3),
  trace("d", "Password reset", 0, 0, 1),
];

describe("filterTraces", () => {
  it("counts a comment-only trace as annotated, so it isn't hidden among untouched traces", () => {
    expect(filterTraces(traces, "annotated", "").map((t) => t.id)).toEqual(["a", "c", "d"]);
    expect(filterTraces(traces, "unannotated", "").map((t) => t.id)).toEqual(["b"]);
  });

  it("combines the filter with a case-insensitive title search", () => {
    expect(filterTraces(traces, "annotated", "REFUND").map((t) => t.id)).toEqual(["a", "c"]);
  });
});

describe("selectRange", () => {
  it("shift-click selects every row between the anchor and the click, in either direction", () => {
    const ids = ["a", "b", "c", "d"];
    expect([...selectRange(ids, new Set(), 3, 1, true)].sort()).toEqual(["b", "c", "d"]);
  });

  it("shift-click on a selected row clears the range instead", () => {
    const ids = ["a", "b", "c", "d"];
    expect([...selectRange(ids, new Set(ids), 0, 2, false)]).toEqual(["d"]);
  });
});

describe("toggleAllVisible", () => {
  // Selecting all under a filter must not drop rows the user picked under a
  // different filter; they're still going to train.
  it("keeps selections hidden by the current filter", () => {
    const next = toggleAllVisible(["a", "c"], new Set(["b"]));
    expect([...next].sort()).toEqual(["a", "b", "c"]);
    expect([...toggleAllVisible(["a", "c"], next)]).toEqual(["b"]);
  });
});

describe("training readiness", () => {
  it("sums labels over the selected rows only", () => {
    expect(summarizeSelection(traces, new Set(["a", "c"]))).toEqual({ count: 2, positive: 2, negative: 3 });
  });

  it("flags a selection that can't possibly make two pairs", () => {
    expect(tooFewPairs({ count: 2, positive: 1, negative: 1 })).toBe(true);
    expect(tooFewPairs({ count: 1, positive: 5, negative: 0 })).toBe(true);
    expect(tooFewPairs({ count: 2, positive: 2, negative: 1 })).toBe(false);
  });
});
