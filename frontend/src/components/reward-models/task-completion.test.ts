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

it("holds estimates between evidence, allows regressions, and breaks at unknowns and new tasks", () => {
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
  expect(completionAt(tasks, 1)?.completion).toBe(0);
  expect(completionAt(tasks, 5)?.completion).toBeNull();
  expect(completionAt(tasks, 7)).toBeNull();
  expect(completionAt(tasks, 8)?.objective).toBe("Second");
  const path = completionPath(tasks, 10);
  expect(path.match(/M/g)).toHaveLength(3);
  expect(path).toContain("V80");
  expect(path).not.toContain("NaN");
});
