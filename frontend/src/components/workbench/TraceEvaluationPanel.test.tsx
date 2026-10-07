import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { wbEvaluation, wbHistoricalEvaluation, wbCreateFeedback, type TraceEvaluation, type TraceEvaluationResponse } from "@/lib/workbench-api";
import TraceEvaluationPanel from "./TraceEvaluationPanel";
vi.mock("@/lib/workbench-api", async (original) => ({ ...await original<typeof import("@/lib/workbench-api")>(), wbEvaluation: vi.fn(), wbHistoricalEvaluation: vi.fn(), wbCreateFeedback: vi.fn() }));
const evaluation: TraceEvaluation = {
  id: "eval-1", trace_id: "trace-1", revision_hash: "rev-1", policy_version: "v1", status: "completed", outcome: "failure", outcome_confidence: 0.93, total_actions: 1, credited_actions: 1, error: null, created_at: "2026-10-06T12:00:00Z", boundary: { kind: "completed_response", step_index: 2 },
  actions: [{ id: "claim", index: 2, content: "All tests passed", tool_name: null }],
  credits: [{ step_id: "claim", index: 2, credit: -2, label: "strongly_negative", confidence: 0.91, call_id: "call-1" }],
  calls: [{ id: "call-1", batch_index: 1, attempt: 1, status: "completed", error: null, input_snapshot: { context_events: [{ id: "result", index: 1, role: "tool", content: "FAILED test_zero" }], omissions: [{ step_id: "old", entire_event: true }] }, raw_output: { choice: "strongly_negative" }, result: {} }],
};
const response: TraceEvaluationResponse = { provider: "jev", model: "jev-1", configured: true, policy_version: "v1", owner_user_id: "owner", boundary: evaluation.boundary, queue: { status: "completed", error: null }, current: evaluation, history: [evaluation] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(wbEvaluation).mockResolvedValue(response); });
it("displays signed action credit separately from confidence and exposes saved evidence", async () => {
  const jump = vi.fn();
  render(<TraceEvaluationPanel traceId="trace-1" onJump={jump} viewerId="owner" />);
  expect(await screen.findByText("failure")).toBeVisible();
  expect(screen.getByText("-2 · strongly negative")).toBeVisible();
  expect(screen.getByText("91%")).toBeVisible();
  expect(screen.getByText("Jev confidence: 93%")).toBeVisible();
  expect(screen.queryByRole("link", { name: /configure.*grader/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Step 3 · response" }));
  expect(jump).toHaveBeenCalledWith("claim");
  fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
  expect(screen.getByText(/Some recorded context was omitted/)).toBeVisible();
  expect(screen.getAllByText(/FAILED test_zero/).length).toBeGreaterThan(0);
});
it("keeps a pending trace distinct from earlier evaluations", async () => {
  vi.mocked(wbEvaluation).mockResolvedValue({ ...response, current: null, boundary: null, queue: { status: "waiting", error: null } });
  vi.mocked(wbHistoricalEvaluation).mockResolvedValue(evaluation);
  render(<TraceEvaluationPanel traceId="trace-1" onJump={vi.fn()} />);
  expect(await screen.findByText(/Waiting for the agent to finish/)).toBeVisible();
  expect(screen.queryByText("failure")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Recorded trace version" }), { target: { value: "eval-1" } });
  expect(await screen.findByText(/Saved evaluation of an earlier trace version/)).toBeVisible();
  expect(screen.getByText("failure")).toBeVisible();
});
it("records a correction against the exact evaluated version", async () => {
  vi.mocked(wbCreateFeedback).mockResolvedValue({ id: "feedback" } as never);
  render(<TraceEvaluationPanel traceId="trace-1" onJump={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Comment" }));
  fireEvent.change(screen.getByRole("textbox", { name: /What should Stash learn/ }), { target: { value: "Verify the zero test." } });
  fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
  await waitFor(() => expect(wbCreateFeedback).toHaveBeenCalledWith({ trace_id: "trace-1", evaluation_id: "eval-1", target_step_id: "claim", comment: "Verify the zero test.", change_kind: "unclear" }));
  expect(await screen.findByText(/Comment saved with this trace version/)).toBeVisible();
});
it("displays provider failure without fabricating a negative outcome", async () => {
  vi.mocked(wbEvaluation).mockResolvedValue({ ...response, current: { ...evaluation, outcome: null, outcome_confidence: null, status: "failed", credited_actions: 0, credits: [], calls: [], error: "Provider unavailable" }, queue: { status: "failed", error: null } });
  render(<TraceEvaluationPanel traceId="trace-1" onJump={vi.fn()} viewerId="owner" />);
  expect(await screen.findByText("evaluation failed")).toBeVisible();
  expect(screen.queryByText("failure")).not.toBeInTheDocument();
  expect(screen.getByText("Not evaluated")).toBeVisible();
  expect(screen.getByRole("button", { name: "Retry evaluation" })).toBeVisible();
});
