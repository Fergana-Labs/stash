import { expect, it } from "vitest";
import type { RmTraceDetail } from "@/lib/types";
import { traceCheckpoint } from "./trace-checkpoint";
it("preserves instructions and prior tool results while excluding the selected action and future events", () => {
  const trace = { id: "trace", steps: [
    { id: "future", index: 3, role: "tool", content: "future result" },
    { id: "system", index: 0, role: "system", content: "rules", metadata: { score: 99 } },
    { id: "target", index: 2, role: "assistant", content: "", tool_name: "search", tool_input: { query: "part" }, tool_call_id: "call" },
    { id: "prior", index: 1, role: "tool", content: "prior result", tool_call_id: "previous" },
  ] } as unknown as RmTraceDetail;
  const checkpoint = traceCheckpoint(trace, "target");
  expect(checkpoint.messages.map((message) => message.id)).toEqual(["system", "prior"]);
  expect(checkpoint.messages[0]).not.toHaveProperty("metadata");
  expect(checkpoint.next_action.tool_input).toEqual({ query: "part" });
  expect(checkpoint.exact_context_window).toBe(false);
  expect(() => traceCheckpoint(trace, "missing")).toThrow("Checkpoint step not found");
});
