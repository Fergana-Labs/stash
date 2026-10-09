import { expect, it } from "vitest";
import { completionAt, completionPath, taskCompletion, type TaskCompletion } from "./task-completion";

it("maps tool-result evidence to the call's displayed row and preserves unknowns", () => {
  const tasks = taskCompletion([{
    first_step_id: "request", last_step_id: "answer", objective: "Refund",
    checkpoints: [
      { step_id: "request", completion: 0, reason: "Requested" },
      { step_id: "call", completion: 0.1, reason: "Attempted" },
      { step_id: "result", completion: 0.4, reason: "Confirmed" },
      { step_id: "answer", completion: null, reason: "Uncertain" },
    ],
  }], new Map([["request", 1], ["call", 2], ["result", 2], ["answer", 3]]));
  expect(tasks[0].checkpoints).toHaveLength(3);
  expect(completionAt(tasks, 1)?.completion).toBe(0.4);
  expect(completionAt(tasks, 2)?.completion).toBeNull();
  expect(completionAt(tasks, 3)).toBeNull();
});

it("smoothly interpolates estimates, allows regressions, and breaks at unknowns and new tasks", () => {
  const tasks: TaskCompletion[] = [
    { first: 0, last: 6, objective: "First", checkpoints: [
      { index: 0, completion: 0, reason: "Requested" },
      { index: 2, completion: 0.6, reason: "Progress" },
      { index: 3, completion: 0.2, reason: "Regression" },
      { index: 4, completion: null, reason: "Unknown" },
      { index: 6, completion: 0.8, reason: "Recovered" },
    ] },
    { first: 8, last: 9, objective: "Second", checkpoints: [{ index: 8, completion: 0, reason: "New request" }] },
  ];
  expect(completionAt(tasks, 1)?.completion).toBeGreaterThan(0);
  expect(completionAt(tasks, 1)?.completion).toBeLessThan(0.6);
  expect(completionAt(tasks, 5)?.completion).toBeNull();
  expect(completionAt(tasks, 7)).toBeNull();
  expect(completionAt(tasks, 8)?.objective).toBe("Second");
  const path = completionPath(tasks, 10);
  expect(path.match(/M/g)).toHaveLength(3);
  expect(path).toContain("C");
  expect(path).not.toContain("V");
  expect(path).not.toContain("NaN");
  const value = (index: number) => completionAt(tasks, index)!.completion!;
  const epsilon = 0.0001;
  expect((value(2) - value(2 - epsilon)) / epsilon).toBeCloseTo(0, 3);
  expect((value(2 + epsilon) - value(2)) / epsilon).toBeCloseTo(0, 3);
  for (let index = 0; index <= 3; index += 0.1) {
    expect(value(index)).toBeGreaterThanOrEqual(0);
    expect(value(index)).toBeLessThanOrEqual(0.6);
  }
});

it("keeps a steady trend straight through checkpoints instead of easing to a stop", () => {
  const tasks: TaskCompletion[] = [{ first: 0, last: 6, objective: "Steady progress", checkpoints: [
    { index: 0, completion: 0, reason: "Start" },
    { index: 3, completion: 0.3, reason: "Progress" },
    { index: 6, completion: 0.6, reason: "More progress" },
  ] }];
  const value = (index: number) => completionAt(tasks, index)!.completion!;
  expect(value(1.5)).toBeCloseTo(0.15);
  expect(value(4.5)).toBeCloseTo(0.45);
  const epsilon = 0.0001;
  expect((value(3) - value(3 - epsilon)) / epsilon).toBeCloseTo(0.1, 5);
  expect((value(3 + epsilon) - value(3)) / epsilon).toBeCloseTo(0.1, 5);
});
