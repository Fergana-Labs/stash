import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { rmGetRewardModel } from "@/lib/api";
import type { RmRewardModelDetail } from "@/lib/types";
import FeedbackDialog from "./FeedbackDialog";

vi.mock("@/lib/api", () => ({ rmGetRewardModel: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it("shows inferred evidence and exclusions even when training failed", async () => {
  vi.mocked(rmGetRewardModel).mockResolvedValue({
    feedback: [{ source: "user_feedback", trace_id: "trace", step_index: 3, label: "unclear", confidence: "low",
      evidence_id: "step:4", evidence_quote: "Thanks, I guess.", reason: "The intent is ambiguous.",
      classifier_model: "classifier", included_in_training: false }],
  } as RmRewardModelDetail);
  render(<FeedbackDialog modelId="model" />);
  expect(rmGetRewardModel).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "View learning" }));
  expect(await screen.findByText("Thanks, I guess.")).toBeVisible();
  expect(screen.getByText(/Excluded from training/)).toBeVisible();
  expect(screen.getByText(/not human ratings/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Response at step 4" })).toHaveAttribute("href", "/reward-models/traces/trace");
});

it("reports a failed fetch rather than claiming no feedback was found", async () => {
  vi.mocked(rmGetRewardModel).mockRejectedValue(new Error("Connection lost"));
  render(<FeedbackDialog modelId="model" />);
  fireEvent.click(screen.getByRole("button", { name: "View learning" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  expect(screen.queryByText(/No supported feedback/)).not.toBeInTheDocument();
});

it("identifies autonomous assessments as AI judgments", async () => {
  vi.mocked(rmGetRewardModel).mockResolvedValue({
    feedback: [{ source: "ai_judgment", trace_id: "trace", step_index: 1, label: "negative", confidence: "high",
      evidence_id: "response:1", evidence_quote: "Refund issued", reason: "No recorded refund action.",
      classifier_model: "classifier", included_in_training: true }],
  } as RmRewardModelDetail);
  render(<FeedbackDialog modelId="model" />);
  fireEvent.click(screen.getByRole("button", { name: "View learning" }));
  expect(await screen.findByText("AI judgment · negative")).toBeVisible();
  expect(screen.getByText(/Included in training data/)).toBeVisible();
});
