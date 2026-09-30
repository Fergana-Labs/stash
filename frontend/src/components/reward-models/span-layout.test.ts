import { describe, expect, it } from "vitest";
import type { RmTraceSpan } from "@/lib/types";
import { layoutSpans } from "./span-layout";

function span(id: string, parent_id: string | null, start: number, end: number): RmTraceSpan {
  const epoch = BigInt("1790708400000000000");
  return { id, parent_id, name: id, kind: "AGENT", start_ns: String(epoch + BigInt(start * 1e6)), end_ns: String(epoch + BigInt(end * 1e6)), input: null, output: null, step_indices: [] };
}

describe("execution timeline", () => {
  const spans = [span("root", null, 0, 100), span("research", "root", 10, 80), span("test", "root", 20, 70), span("search", "research", 15, 30)];
  it("preserves overlap and parent hierarchy rather than placing agents sequentially", () => {
    const layout = layoutSpans(spans, new Set());
    expect(layout.durationMs).toBe(100);
    expect(layout.rows.map(r => [r.span.id, r.depth, r.startMs, r.durationMs])).toEqual([
      ["root", 0, 0, 100], ["research", 1, 10, 70], ["search", 2, 15, 15], ["test", 1, 20, 50],
    ]);
  });
  it("collapses descendants without changing the time scale or hiding concurrent siblings", () => {
    const layout = layoutSpans(spans, new Set(["research"]));
    expect(layout.rows.map(r => r.span.id)).toEqual(["root", "research", "test"]);
    expect(layout.durationMs).toBe(100);
  });
  it("shows a received child even when its parent span has not arrived yet", () => {
    expect(layoutSpans([span("child", "pending", 10, 20)], new Set()).rows[0].depth).toBe(0);
  });
  it("does not invent a timeline for untimed messages", () => {
    expect(layoutSpans([], new Set())).toEqual({ rows: [], durationMs: 0 });
  });
});
