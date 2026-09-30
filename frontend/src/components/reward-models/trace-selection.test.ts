import { describe, expect, it } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import { searchTraces, selectRange, sortTraces, summarizeSelection, toggleAllVisible, tooFewPairs } from "./trace-selection";

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

describe("sortTraces", () => {
  it("orders numeric columns numerically and leaves the original list intact", () => {
    const rows = [{ ...traces[0], step_count: 20 }, { ...traces[1], step_count: 3 }];
    expect(sortTraces(rows, "steps", "ascending").map((t) => t.id)).toEqual(["b", "a"]);
    expect(rows.map((t) => t.id)).toEqual(["a", "b"]);
    expect(sortTraces(traces, "labels", "descending").map((t) => t.id)).toEqual(["c", "a", "b", "d"]);
  });

  it("keeps unscored traces last while respecting zero and negative rewards", () => {
    const rows = [traces[0], ...[0, -2].map((score, i) => ({
      ...traces[i + 1], latest_score: { reward_model_id: "model", reward_model_name: "Model", score },
    }))];
    expect(sortTraces(rows, "reward", "ascending").map((t) => t.id)).toEqual(["c", "b", "a"]);
    expect(sortTraces(rows, "reward", "descending").map((t) => t.id)).toEqual(["b", "c", "a"]);
  });

  it("sorts imported dates by the actual instant, including timezone offsets", () => {
    const rows = [{ ...traces[0], created_at: "2026-09-29T09:00:00+02:00" }, { ...traces[1], created_at: "2026-09-29T08:00:00Z" }];
    expect(sortTraces(rows, "imported", "descending").map((t) => t.id)).toEqual(["b", "a"]);
    expect(sortTraces(traces, "title", "ascending").map((t) => t.id)).toEqual(["d", "c", "a", "b"]);
  });
});

describe("searchTraces", () => {
  it("searches titles without excluding traces based on comments or ratings", () => {
    expect(searchTraces(traces, "")).toEqual(traces);
    expect(searchTraces(traces, " REFUND ").map((t) => t.id)).toEqual(["a", "c"]);
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
