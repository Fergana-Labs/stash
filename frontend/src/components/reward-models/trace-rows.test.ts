import { describe, expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { buildRows, rowSteps, toolSummary } from "./trace-rows";

function step(index: number, role: RmStep["role"], extra: Partial<RmStep> = {}): RmStep {
  return {
    id: `s${index}`,
    index,
    role,
    content: "",
    tool_name: null,
    tool_input: null,
    tool_call_id: null,
    metadata: null,
    ...extra,
  };
}

describe("buildRows", () => {
  const steps = [
    step(0, "system", { content: "You are a support agent." }),
    step(1, "user", { content: "Refund order B2204?" }),
    step(2, "assistant", { tool_name: "lookup_order", tool_input: { order_id: "B2204" }, tool_call_id: "c1" }),
    step(3, "assistant", { tool_name: "check_policy", tool_input: {}, tool_call_id: "c2" }),
    step(4, "tool", { tool_name: "check_policy", tool_call_id: "c2", content: "30 days" }),
    step(5, "tool", { tool_name: "lookup_order", tool_call_id: "c1", content: "{\"status\": \"delivered\"}" }),
    step(6, "assistant", { content: "Sorry, it's past 30 days." }),
    step(7, "user", { content: "Please?" }),
  ];
  const rows = buildRows(steps);

  // Every step must still appear exactly once, or its annotations would have
  // nowhere to render and its + / − buttons would vanish.
  it("keeps every step exactly once across rows", () => {
    expect(rows.flatMap(rowSteps).map((s) => s.id).sort()).toEqual(steps.map((s) => s.id).sort());
  });

  it("pairs only adjacent calls and results, preserving out-of-order arrival", () => {
    const tools = rows.filter((r) => r.kind === "tool");
    expect(tools.map((r) => [r.call?.id, r.result?.id])).toEqual([
      ["s2", undefined],
      ["s3", "s4"],
      [undefined, "s5"],
    ]);
  });

  it("never moves a result ahead of intervening events", () => {
    expect(rows.flatMap(rowSteps)).toEqual(steps);
    const interrupted = [steps[2], step(3, "system", { content: "Interrupted" }), steps[5]];
    expect(buildRows(interrupted).flatMap(rowSteps)).toEqual(interrupted);
  });

  it("numbers turns by user prompts", () => {
    expect(rows.filter((r) => r.kind === "prompt").map((r) => r.turn)).toEqual([1, 2]);
  });

  it("shows a result with no matching call as its own row", () => {
    const orphan = buildRows([step(0, "tool", { tool_call_id: "x", content: "ok" })]);
    expect(orphan).toEqual([{ kind: "tool", key: "s0", call: null, result: expect.objectContaining({ id: "s0" }) }]);
  });

  it("groups adjacent calls and outputs by exact tool name when both IDs are absent", () => {
    const source = [
      step(0, "assistant", { tool_name: "find_parts_for_vehicle", tool_input: { part_description: "wiper blade" } }),
      step(1, "tool", { tool_name: "find_parts_for_vehicle", content: "## ford-parts — Ford Parts" }),
      step(2, "assistant", { tool_name: "find_parts_for_vehicle", tool_input: { part_description: "wiper arm" } }),
      step(3, "tool", { tool_name: "find_parts_for_vehicle", content: "Wiper arm found" }),
    ];
    const snapshot = structuredClone(source);
    const grouped = buildRows(source);
    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ call: source[0], result: source[1] });
    expect(grouped[1]).toMatchObject({ call: source[2], result: source[3] });
    expect(grouped.flatMap(rowSteps)).toEqual(source);
    expect(source).toEqual(snapshot);
  });

  it.each([
    [null, null, "other_tool"],
    [undefined, undefined, "other_tool"],
    [null, null, null],
    ["call1", "call2", "lookup"],
    ["call1", null, "lookup"],
    [null, "call1", "lookup"],
  ])("does not infer a pair across conflicting names or IDs: %s, %s, %s", (callId, resultId, resultName) => {
    const source = [
      step(0, "assistant", { tool_name: "lookup", tool_call_id: callId }),
      step(1, "tool", { tool_name: resultName, tool_call_id: resultId, content: "Found" }),
    ];
    expect(buildRows(source)).toHaveLength(2);
    expect(buildRows(source).flatMap(rowSteps)).toEqual(source);
  });

  it("leaves overlapping calls to the same tool separate until their outputs arrive", () => {
    const source = [
      step(0, "assistant", { tool_name: "lookup" }),
      step(1, "assistant", { tool_name: "lookup" }),
      step(2, "tool", { tool_name: "lookup", content: "One result" }),
      step(3, "tool", { tool_name: "lookup", content: "Another result" }),
      step(4, "assistant", { tool_name: "lookup" }),
      step(5, "tool", { tool_name: "lookup", content: "Unambiguous result" }),
    ];
    const grouped = buildRows(source);
    expect(grouped).toHaveLength(5);
    expect(grouped[1]).toMatchObject({ call: source[1], result: null });
    expect(grouped[4]).toMatchObject({ call: source[4], result: source[5] });
    expect(grouped.flatMap(rowSteps)).toEqual(source);
  });

  it("does not infer an anonymous pair while an identified call to the same tool is outstanding", () => {
    const source = [
      step(0, "assistant", { tool_name: "lookup", tool_call_id: "earlier" }),
      step(1, "assistant", { tool_name: "lookup" }),
      step(2, "tool", { tool_name: "lookup", content: "Unknown caller" }),
    ];
    expect(buildRows(source)).toHaveLength(3);
  });

  it("keeps an anonymous output in place when another event separates it from the call", () => {
    const source = [
      step(0, "assistant", { tool_name: "lookup" }),
      step(1, "user", { content: "Wait" }),
      step(2, "tool", { tool_name: "lookup", content: "Found" }),
    ];
    expect(buildRows(source)).toHaveLength(3);
    expect(buildRows(source).flatMap(rowSteps)).toEqual(source);
  });
});

describe("toolSummary", () => {
  it("prefers the field that says what the call did", () => {
    expect(toolSummary({ timeout: 30, command: "ls -la\nsecond line" })).toBe("ls -la");
  });

  it("falls through to key=value pairs for tools it doesn't know", () => {
    expect(toolSummary({ order_id: "B2204", verbose: true })).toBe("order_id=B2204  verbose=true");
  });
});
