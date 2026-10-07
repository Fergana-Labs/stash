import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { wbAssessments, wbCreateFeedback, type Assessment, type AssessmentResponse } from "@/lib/workbench-api";
import type { RmStep } from "@/lib/types";
import AssessmentInspector from "./AssessmentInspector";

vi.mock("@/lib/workbench-api", async (original) => ({ ...await original<typeof import("@/lib/workbench-api")>(), wbAssess: vi.fn(), wbAssessments: vi.fn(), wbCreateFeedback: vi.fn() }));

const assessment: Assessment = { id: "assessment-1", trace_id: "trace-1", target_step_id: "claim", target_index: 2, grader_id: "grader-1", grader_version_id: "version-1", criterion_id: "test_reporting", criterion_name: "Accurate test reports", status: "completed", verdict: "meets", reason: null, evidence_step_ids: [], input_snapshot: { context_events: [{ id: "result", content: "FAILED test_zero" }, { id: "claim", content: "All tests pass" }], omissions: [{ step_id: "earlier", reason: "context_budget" }] }, raw_output: { decision: "meets" }, error: null, created_at: "2026-10-06T12:00:00Z" };
const steps = [{ id: "result", index: 1, role: "tool", content: "FAILED test_zero", tool_name: "pytest" }, { id: "claim", index: 2, role: "assistant", content: "All tests pass" }] as RmStep[];
const response: AssessmentResponse = { assessments: [assessment], coverage: { total_actions: 3, assessed_actions: 1, pending: 0, failed: 0 }, graders: [], owner_user_id: "owner" };

beforeEach(() => { vi.clearAllMocks(); vi.mocked(wbAssessments).mockResolvedValue(response); });

it("shows saved input separately from citations and keeps the prediction when saving a correction", async () => {
  vi.mocked(wbCreateFeedback).mockResolvedValue({ id: "feedback-1" } as never);
  const jump = vi.fn();
  render(<AssessmentInspector traceId="trace-1" steps={steps} onJump={jump} viewerId="owner" />);
  expect(await screen.findByText(/1 \/ 3 actions assessed/)).toBeVisible();
  expect(screen.getByText(/without a written explanation/)).toBeVisible();
  expect(screen.queryByText("Cited evidence")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Selected context (2 events)"));
  expect(screen.getByText(/not model-generated citations/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /Step 2 · tool/ }));
  expect(jump).toHaveBeenCalledWith("result");
  expect(screen.getByText(/1 recorded omission/)).toBeVisible();
  fireEvent.click(screen.getByText("Correct this assessment or agent behavior"));
  fireEvent.change(screen.getByRole("textbox", { name: /What was wrong/ }), { target: { value: "The zero test failed." } });
  fireEvent.change(screen.getByRole("combobox", { name: "Correct verdict" }), { target: { value: "violates" } });
  fireEvent.change(screen.getByRole("combobox", { name: "What needs to change?" }), { target: { value: "both" } });
  fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
  await waitFor(() => expect(wbCreateFeedback).toHaveBeenCalledWith({ trace_id: "trace-1", assessment_id: "assessment-1", target_step_id: "claim", comment: "The zero test failed.", proposed_verdict: "violates", change_kind: "both" }));
  expect(await screen.findByRole("status")).toHaveTextContent("original prediction is retained");
  expect(screen.getAllByText("meets")).toHaveLength(2);
});

it("shows failed execution as an error rather than a negative agent verdict", async () => {
  vi.mocked(wbAssessments).mockResolvedValue({ ...response, assessments: [{ ...assessment, status: "failed", verdict: null, error: "Provider timed out" }], coverage: { ...response.coverage, failed: 1, last_error: "Grading budget reached" } });
  render(<AssessmentInspector traceId="trace-1" steps={steps} onJump={vi.fn()} viewerId="reviewer" />);
  expect(await screen.findByText(/This is not a verdict on the agent/)).toBeVisible();
  expect(screen.getByText("Grading budget reached")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Assess saved trace" })).not.toBeInTheDocument();
});

it("historical records do not require grader configuration or manual scheduling", async () => {
  vi.mocked(wbAssessments).mockResolvedValue({ ...response, assessments: [] });
  render(<AssessmentInspector traceId="trace-1" steps={steps} onJump={vi.fn()} viewerId="owner" />);
  expect(await screen.findByText(/No earlier rubric assessments/)).toBeVisible();
  expect(screen.queryByRole("link", { name: "Graders" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Assess saved trace" })).not.toBeInTheDocument();
});
