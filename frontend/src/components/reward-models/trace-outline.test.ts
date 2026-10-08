import { describe, expect, it } from "vitest";
import type { RmStep } from "@/lib/types";
import { buildTraceLabels } from "./step-labels";
import { buildOutline, defaultOpen, outlinePath } from "./trace-outline";
import { buildRows } from "./trace-rows";

function step(index: number, role: RmStep["role"], label: Record<string, unknown> | null, overrides: Partial<RmStep> = {}): RmStep {
  return { id: `s${index}`, index, role, content: "", tool_name: null, tool_input: null, tool_call_id: null, metadata: label === null ? null : { label }, ...overrides };
}

const user = (chunk: string, task: string, extra: Record<string, unknown> = {}) => ({ chunk_id: chunk, task_id: task, actor: "user", intent: "new_request", verdict: "none", ...extra });
const call = (chunk: string, task: string, extra: Record<string, unknown> = {}) => ({ chunk_id: chunk, task_id: task, actor: "agent", type: "tool_call", effect: "read", result: "data", is_output: false, ...extra });
const answer = (chunk: string, task: string, extra: Record<string, unknown> = {}) => ({ chunk_id: chunk, task_id: task, actor: "agent", type: "message", is_output: true, outcome: "answer", stance: "confident", ...extra });
const tool = (index: number, label: Record<string, unknown>) => step(index, "assistant", label, { tool_name: "search", tool_input: {}, tool_call_id: `c${index}` });

function outlineOf(steps: RmStep[], scores = [] as Parameters<typeof buildOutline>[2]) {
  return buildOutline(buildRows(steps), buildTraceLabels(steps), scores);
}

const steps = [
  step(0, "user", user("u1", "t1"), { content: "Find the supplier for part 12" }),
  tool(1, call("a1", "t1")),
  tool(2, call("a2", "t1", { result: "error" })),
  step(3, "assistant", answer("a3", "t1"), { content: "It is Acme." }),
  step(4, "user", user("u2", "t1", { intent: "correction", verdict: "rejected", verdict_target: "a3" }), { content: "That is the wrong one" }),
  tool(5, call("a4", "t1", { duplicate_of: "a1" })),
  step(6, "assistant", answer("a5", "t1"), { content: "It is Bolt." }),
  step(7, "user", user("u3", "t2"), { content: "Now email them" }),
  tool(8, call("a6", "t2", { effect: "side_effect" })),
];

describe("buildOutline", () => {
  it("splits a trace into tasks, and each task into one turn per user message", () => {
    const outline = outlineOf(steps);
    expect(outline.map((task) => [task.number, task.title, task.turns.length, task.steps])).toEqual([
      [1, "Find the supplier for part 12", 2, 7],
      [2, "Now email them", 1, 2],
    ]);
    expect(outline[0].turns.map((turn) => turn.preview)).toEqual(["Find the supplier for part 12", "That is the wrong one"]);
  });

  it("summarizes the agent's work in each turn", () => {
    const outline = outlineOf(steps);
    expect(outline[0].turns[0].work).toBe("2 lookups · 1 error");
    expect(outline[0].turns[1].work).toBe("1 lookup · 1 repeat");
    expect(outline[1].turns[0].work).toBe("1 action");
  });

  it("shows each turn's answer, and the task's last answer on the task", () => {
    const outline = outlineOf(steps);
    const first = outline[0].turns[0].answerChips.map((chip) => chip.text);
    expect(first.some((text) => text.startsWith("Rejected"))).toBe(true);
    expect(outline[0].answerChips).toEqual(outline[0].turns[1].answerChips);
    expect(outline[1].answerChips).toEqual([]);
  });

  it("attaches each task's score by task id", () => {
    const score = { task: "t2", score: -0.05, rubricOnly: -0.05, answer: null, costs: -0.05, hasAnswer: false };
    const outline = outlineOf(steps, [score]);
    expect(outline[0].score).toBeNull();
    expect(outline[1].score).toEqual(score);
  });

  it("keeps a double-logged user message in one turn", () => {
    const twice = [
      step(0, "user", user("u1", "t1"), { content: "hello" }),
      step(1, "user", user("u1", "t1"), { content: "hello" }),
      tool(2, call("a1", "t1")),
    ];
    expect(outlineOf(twice)[0].turns).toHaveLength(1);
  });

  it("adds up the step scores in a turn", () => {
    const scored = [
      step(0, "user", user("u1", "t1"), { content: "hello" }),
      { ...tool(1, call("a1", "t1")), metadata: { label: call("a1", "t1"), reward: { base: -0.03, score: -0.03, total: -0.03 } } },
      { ...tool(2, call("a2", "t1")), metadata: { label: call("a2", "t1"), reward: { base: -0.1, score: -0.1, total: -0.1 } } },
    ];
    expect(outlineOf(scored)[0].turns[0].points).toBeCloseTo(-0.13);
    expect(outlineOf(steps)[0].turns[0].points).toBeNull();
  });

  it("puts steps before the first user message in a setup turn", () => {
    const outline = outlineOf([step(0, "system", null, { content: "You are an agent" }), ...steps.map((s) => ({ ...s, index: s.index + 1 }))]);
    expect(outline[0].turns[0].prompt).toBeNull();
    expect(outline[0].title).toBe("Find the supplier for part 12");
  });
});

describe("outlinePath", () => {
  it("names the task and turn that hold a step", () => {
    const outline = outlineOf(steps);
    expect(outlinePath(outline, "s5")).toEqual(["task-t1", "task-t1-turn-2"]);
    expect(outlinePath(outline, "missing")).toEqual([]);
  });
});

describe("defaultOpen", () => {
  it("opens a short trace fully and leaves a long one as a list of tasks", () => {
    const short = outlineOf(steps.slice(0, 4));
    expect([...defaultOpen(short)]).toEqual(["task-t1", "task-t1-turn-1"]);
    const two = outlineOf(steps);
    expect([...defaultOpen(two)]).toEqual(["task-t1", "task-t2"]);
    const many = outlineOf([...steps, step(9, "user", user("u4", "t3"), { content: "And one more" })]);
    expect(defaultOpen(many).size).toBe(0);
  });
});
