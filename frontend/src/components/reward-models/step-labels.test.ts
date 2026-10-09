import { describe, expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { buildTraceLabels, stepLabel } from "./step-labels";

function step(index: number, role: RmStep["role"], label: Record<string, unknown> | null, overrides: Partial<RmStep> = {}): RmStep {
  return {
    id: `s${index}`,
    index,
    role,
    content: "",
    tool_name: null,
    tool_input: null,
    tool_call_id: null,
    metadata: label === null ? null : { label },
    ...overrides,
  };
}

const user = (chunk: string, extra: Record<string, unknown> = {}) => ({ chunk_id: chunk, task_id: "t1", actor: "user", intent: "new_request", verdict: "none", ...extra });
const agent = (chunk: string, extra: Record<string, unknown> = {}) => ({ chunk_id: chunk, task_id: "t1", actor: "agent", type: "tool_call", effect: "read", result: "data", is_output: false, ...extra });

describe("stepLabel", () => {
  it("reads a label from step metadata and ignores anything that is not one", () => {
    expect(stepLabel(step(0, "user", user("u1")))?.intent).toBe("new_request");
    expect(stepLabel(step(0, "user", null))).toBeNull();
    expect(stepLabel(step(0, "user", { actor: "user" }))).toBeNull();
    expect(stepLabel(step(0, "user", { chunk_id: "u1", actor: "robot" }))).toBeNull();
  });
});

describe("buildTraceLabels", () => {
  it("is absent for a trace with no labels", () => {
    const labels = buildTraceLabels([step(0, "user", null), step(1, "assistant", null)]);
    expect(labels.present).toBe(false);
    expect(labels.summary).toEqual([]);
    expect(labels.chips(step(0, "user", null))).toEqual([]);
  });

  it("keeps an ordinary read quiet and flags the exceptions", () => {
    const steps = [
      step(0, "user", user("u1")),
      step(1, "assistant", agent("a1")),
      step(2, "assistant", agent("a2", { result: "empty" })),
      step(3, "assistant", agent("a3", { result: "error" })),
      step(4, "assistant", agent("a4", { duplicate_of: "a1" })),
      step(5, "assistant", agent("a5", { effect: "side_effect" })),
    ];
    const labels = buildTraceLabels(steps);
    expect(labels.chips(steps[1])).toEqual([]);
    expect(labels.chips(steps[2]).map((c) => c.text)).toEqual(["Returned nothing useful"]);
    expect(labels.chips(steps[3]).map((c) => c.text)).toEqual(["Returned an error"]);
    expect(labels.chips(steps[4])).toEqual([expect.objectContaining({ text: "Same call as step 2", targetStepId: "s1" })]);
    expect(labels.chips(steps[5]).map((c) => c.text)).toEqual(["Changes something"]);
  });

  it("links a user verdict and the output it judges in both directions", () => {
    const steps = [
      step(0, "user", user("u1")),
      step(1, "assistant", agent("a1", { is_output: true, outcome: "answer", stance: "hedged", coverage: "1/1" })),
      step(2, "user", user("u2", { intent: "correction", verdict: "rejected", verdict_target: "a1", sentiment: "negative" })),
    ];
    const labels = buildTraceLabels(steps);
    expect(labels.chips(steps[1])).toEqual([
      expect.objectContaining({ text: "Answer given" }),
      expect.objectContaining({ text: "With caveats" }),
      expect.objectContaining({ text: "1 of 1 item" }),
      expect.objectContaining({ text: "Rejected by the user in step 3", tone: "bad", targetStepId: "s2" }),
    ]);
    expect(labels.chips(steps[2])).toEqual([
      expect.objectContaining({ text: "Corrects the agent", tone: "bad" }),
      expect.objectContaining({ text: "Rejects the answer in step 2", tone: "bad", targetStepId: "s1" }),
      expect.objectContaining({ text: "Negative tone" }),
    ]);
  });

  it("shows a verdict without a link when its target is not in the trace", () => {
    const steps = [step(0, "user", user("u1", { verdict: "confirmed", verdict_target: "a9" }))];
    const [, verdict] = buildTraceLabels(steps).chips(steps[0]);
    expect(verdict).toEqual(expect.objectContaining({ text: "Confirms the answer" }));
    expect(verdict.targetStepId).toBeUndefined();
  });

  it("names tasks only when the trace has more than one", () => {
    const one = [step(0, "user", user("u1")), step(1, "assistant", agent("a1"))];
    expect(buildTraceLabels(one).taskHeading(one[0])).toBeNull();

    const two = [...one, step(2, "user", user("u2", { task_id: "t2" })), step(3, "assistant", agent("a2", { task_id: "t2" }))];
    const labels = buildTraceLabels(two);
    expect(labels.taskHeading(two[0])).toBe("Task 1");
    expect(labels.taskHeading(two[1])).toBeNull();
    expect(labels.taskHeading(two[2])).toBe("Task 2");
  });

  it("excludes context-only task IDs from visible task numbers and counts", () => {
    const steps = [
      step(0, "user", user("u1", { intent: "added_context" })),
      step(1, "user", user("u2", { task_id: "t2" })),
      step(2, "assistant", agent("a1", { task_id: "t2" })),
      step(3, "user", user("u3", { task_id: "t3" })),
    ];
    const labels = buildTraceLabels(steps);
    expect(labels.taskHeading(steps[0])).toBe("Context");
    expect(labels.taskHeading(steps[1])).toBe("Task 1");
    expect(labels.taskName(steps[2])).toBe("Task 1");
    expect(labels.taskHeading(steps[3])).toBe("Task 2");
    expect(labels.label(steps[2])?.task_id).toBe("t2");
    expect(labels.summary.find((item) => item.key === "tasks")).toEqual(expect.objectContaining({ text: "2 tasks", stepIds: ["s1", "s3"] }));
    // Context inside an actual task remains part of that task.
    const mixed = buildTraceLabels([steps[0], step(1, "assistant", agent("a1"))]);
    expect(mixed.taskName(steps[0])).toBe("Task 1");
  });

  it("summarises counts with the steps to jump to, in trace order", () => {
    const steps = [
      step(0, "user", user("u1")),
      step(1, "assistant", agent("a1", { type: "clarifying_question", effect: null, result: null })),
      step(2, "assistant", agent("a2", { result: "error" })),
      step(3, "assistant", agent("a3", { result: "error" })),
      step(4, "assistant", agent("a4", { is_output: true, outcome: "not_found", stance: "asserted", coverage: "0/1" })),
    ];
    const summary = buildTraceLabels(steps).summary;
    expect(summary.map((item) => item.text)).toEqual(["1 answer", "1 question to the user", "2 tool errors"]);
    expect(summary.find((item) => item.key === "errors")?.stepIds).toEqual(["s2", "s3"]);
  });
});

describe("chip tooltips", () => {
  it("explains every chip, and quotes the labeler's evidence where there is some", () => {
    const steps = [
      step(0, "user", user("u1", { intent: "repeat_request", evidence: "please look again" })),
      step(1, "assistant", agent("a1", { result: "error" })),
    ];
    const labels = buildTraceLabels(steps);
    const [asksAgain] = labels.chips(steps[0]);
    expect(asksAgain.text).toBe("Asks again");
    expect(asksAgain.title).toContain("counts as rejecting the previous answer");
    expect(asksAgain.title).toContain("“please look again”");
    expect(labels.chips(steps[1]).every((chip) => chip.title.length > 0)).toBe(true);
  });
});
