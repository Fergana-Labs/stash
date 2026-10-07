import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { wbReviewFeedback, type WorkbenchFeedback } from "@/lib/workbench-api";
import FeedbackReview from "./FeedbackReview";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/workbench-api", async (original) => ({ ...await original<typeof import("@/lib/workbench-api")>(), wbReviewFeedback: vi.fn() }));
const feedback: WorkbenchFeedback = { id: "feedback", trace_id: "trace", assessment_id: "assessment", target_step_id: "claim", comment: "The test failed; the claim was wrong.", proposed_verdict: "violates", change_kind: "unclear", interpretation: { explanation: "Ambiguous feedback" }, review_status: "pending", status: "completed", author_user_id: "sam", source: "human_comment", created_at: "2026-10-06T12:00:00Z" };
beforeEach(() => vi.clearAllMocks());

it("requires resolving an ambiguous interpretation and sends an explicit human review", async () => {
  vi.mocked(wbReviewFeedback).mockResolvedValue({ ...feedback, review_status: "accepted" });
  const reload = vi.fn().mockResolvedValue(undefined);
  render(<FeedbackReview feedback={feedback} onReviewed={reload} />);
  expect(screen.getByRole("button", { name: "Accept interpretation and prepare changes" })).toBeDisabled();
  expect(screen.getByRole("link", { name: "Open source trace →" })).toHaveAttribute("href", "/reward-models/traces/trace#step-claim");
  fireEvent.change(screen.getByRole("combobox", { name: "Reviewed interpretation" }), { target: { value: "both" } });
  fireEvent.click(screen.getByRole("button", { name: "Accept interpretation and prepare changes" }));
  await waitFor(() => expect(wbReviewFeedback).toHaveBeenCalledWith("feedback", { decision: "accept", proposed_verdict: "violates", change_kind: "both" }));
  expect(reload).toHaveBeenCalledTimes(1);
});

it("keeps an unprocessed interpretation out of accepted human labels", () => {
  render(<FeedbackReview feedback={{ ...feedback, change_kind: "both", status: "running" }} onReviewed={vi.fn()} />);
  expect(screen.getByText("Preparing interpretation…")).toBeVisible();
  expect(screen.getByRole("button", { name: "Accept interpretation and prepare changes" })).toBeDisabled();
});

it("links an extracted correction separately from the earlier action it corrects", () => {
  render(<FeedbackReview feedback={{ ...feedback, source: "trace_extraction", source_event_id: "user-correction" }} onReviewed={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Open source correction →" })).toHaveAttribute("href", "/reward-models/traces/trace#step-user-correction");
  expect(screen.getByRole("link", { name: "Open target action →" })).toHaveAttribute("href", "/reward-models/traces/trace#step-claim");
  expect(screen.queryByRole("link", { name: "Open source trace →" })).not.toBeInTheDocument();
});

it("links a new requirement to its source user message even without a target action", () => {
  render(<FeedbackReview feedback={{ ...feedback, source: "trace_extraction", source_event_id: "new-requirement", target_step_id: null, assessment_id: null, proposed_verdict: null, change_kind: "requirement_change" }} onReviewed={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Open source correction →" })).toHaveAttribute("href", "/reward-models/traces/trace#step-new-requirement");
  expect(screen.queryByRole("link", { name: "Open target action →" })).not.toBeInTheDocument();
});

it("preserves the trace link for manual feedback without an event anchor", () => {
  render(<FeedbackReview feedback={{ ...feedback, source_event_id: null, target_step_id: null }} onReviewed={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Open source trace →" })).toHaveAttribute("href", "/reward-models/traces/trace");
  expect(screen.queryByRole("link", { name: "Open target action →" })).not.toBeInTheDocument();
});

it("does not duplicate the source link when the stored target is the same event", () => {
  render(<FeedbackReview feedback={{ ...feedback, source_event_id: "claim" }} onReviewed={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Open source correction →" })).toHaveAttribute("href", "/reward-models/traces/trace#step-claim");
  expect(screen.queryByRole("link", { name: "Open target action →" })).not.toBeInTheDocument();
});

it("allows accepting an interpretation without promising a change when repository scope is absent", async () => {
  const blockReason = "This trace has no recorded repository directory. The interpretation is saved, but no instruction change can be created without a repository scope.";
  vi.mocked(wbReviewFeedback).mockResolvedValue({ ...feedback, review_status: "accepted" });
  render(<FeedbackReview feedback={{ ...feedback, assessment_id: null, proposed_verdict: null, change_kind: "both", interpretation: { explanation: "Verify tests", instruction_draft_blocked_reason: blockReason } }} onReviewed={vi.fn().mockResolvedValue(undefined)} />);
  expect(screen.getByRole("status")).toHaveTextContent(blockReason);
  expect(screen.queryByRole("button", { name: "Accept interpretation and prepare changes" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Accept interpretation" }));
  await waitFor(() => expect(wbReviewFeedback).toHaveBeenCalledWith("feedback", { decision: "accept", change_kind: "both" }));
});
