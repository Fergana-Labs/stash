import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import type { TraceEvaluation, TraceEvaluationResponse } from "@/lib/workbench-api";
import TraceScore from "./TraceScore";

const boundary = { kind: "response", step_index: 2 };
const current = (overrides: Partial<TraceEvaluation> = {}): TraceEvaluation => ({
  id: "current", trace_id: "trace", revision_hash: "revision", policy_version: "policy", status: "running",
  outcome: null, outcome_probabilities: null, outcome_confidence: null, total_actions: 2, credited_actions: 0,
  error: null, created_at: "2026-10-07", boundary, credits: [], actions: [], calls: [], ...overrides,
});
const evaluation = (overrides: Partial<TraceEvaluationResponse> = {}): TraceEvaluationResponse => ({
  provider: "automatic", model: "classifier", configured: true, policy_version: "policy", owner_user_id: "owner",
  boundary, queue: null, current: null, history: [], ...overrides,
});
const history: TraceEvaluationResponse["history"] = [{ id: "old", status: "completed", outcome: "success", created_at: "2026-10-07", boundary }];

it("distinguishes initial loading from recalculation after the trace grows, then shows the new score", () => {
  const view = render(<TraceScore evaluation={null} error={null} />);
  expect(screen.getByRole("status", { name: "Trace score" })).toHaveTextContent("Loading…");
  view.rerender(<TraceScore evaluation={evaluation({ history, queue: { status: "queued", error: null } })} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("Recalculation queued");
  view.rerender(<TraceScore evaluation={evaluation({ history, current: current(), queue: { status: "running", error: null } })} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("Recalculating…");
  // A zero score is valid; action annotations can still be running after it arrives.
  view.rerender(<TraceScore evaluation={evaluation({ history, current: current({ outcome: "failure", outcome_probabilities: { success: 0 } }), queue: { status: "running", error: null } })} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("0.00");
  expect(screen.queryByText("Recalculating…")).toBeNull();
});

it("calls a first evaluation scoring, not recalculating", () => {
  render(<TraceScore evaluation={evaluation({ current: current(), queue: { status: "running", error: null } })} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("Scoring…");
});

it.each([
  [evaluation({ queue: { status: "failed", error: "Evaluation failed" } }), "Scoring failed"],
  [evaluation({ boundary: null, queue: { status: "waiting", error: null } }), "Waiting for response"],
  [evaluation({ configured: false }), "Unavailable"],
  [evaluation(), "Awaiting score"],
] as const)("does not present an inactive scoring state as recalculation: %s", (data, label) => {
  render(<TraceScore evaluation={data} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent(label);
  expect(screen.getByRole("status").querySelector("svg")).toBeNull();
});

it("shows insufficient evidence instead of a number or a historical verdict", () => {
  render(<TraceScore evaluation={evaluation({ history, current: current({ outcome: "insufficient_evidence", outcome_probabilities: { success: 0.2 } }) })} error={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("Insufficient evidence");
  expect(screen.queryByText("0.20")).toBeNull();
});

it("explains fetch failures and keeps an already loaded numeric score visible", () => {
  const view = render(<TraceScore evaluation={null} error="Network error" />);
  expect(screen.getByRole("status")).toHaveTextContent("Couldn't load");
  view.rerender(<TraceScore evaluation={evaluation({ current: current({ outcome: "success", outcome_probabilities: { success: 0.8 } }) })} error="Network error" />);
  expect(screen.getByRole("status")).toHaveTextContent("0.80");
  expect(screen.getByRole("status")).toHaveTextContent("Update unavailable");
});
