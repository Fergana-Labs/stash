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

  it("pairs each call with its result by tool_call_id, even when results arrive out of order", () => {
    const tools = rows.filter((r) => r.kind === "tool");
    expect(tools.map((r) => [r.call?.id, r.result?.id])).toEqual([
      ["s2", "s5"],
      ["s3", "s4"],
    ]);
  });

  it("numbers turns by user prompts", () => {
    expect(rows.filter((r) => r.kind === "prompt").map((r) => r.turn)).toEqual([1, 2]);
  });

  it("shows a result with no matching call as its own row", () => {
    const orphan = buildRows([step(0, "tool", { tool_call_id: "x", content: "ok" })]);
    expect(orphan).toEqual([{ kind: "tool", key: "s0", call: null, result: expect.objectContaining({ id: "s0" }) }]);
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
