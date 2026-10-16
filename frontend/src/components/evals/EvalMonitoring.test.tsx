import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import EvalMonitoring from "./EvalMonitoring";

const api = vi.hoisted(() => ({ imMonitoring: vi.fn(), imCredit: vi.fn(), imStartRefine: vi.fn(), imSetAlert: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);

const empty = { calls: 0, errors: 0, with_feedback: 0, accuracy: null, ece: null, mean_confidence: null, mean_value: null };

beforeEach(() => {
  vi.clearAllMocks();
  api.imCredit.mockResolvedValue({ decisions: ["good", "bad"], runs: 2, calls: 2, success_rate: 0.5, minimum_runs: 6, by_decision: [{ decision: "good", runs: 1, success_rate: 1 }, { decision: "bad", runs: 1, success_rate: 0 }], ready: false, reason: "Needs at least 6 runs with outcomes, including successes and failures" });
});

it("explains that accuracy needs feedback when there are calls but no feedback", async () => {
  api.imMonitoring.mockResolvedValue({ days: 30, truncated: false, summary: { ...empty, calls: 4, errors: 1, reliability: [] }, daily: [{ date: "2026-10-12", ...empty, calls: 4, errors: 1, labels: { good: 3 } }], versions: [{ version: 2, ...empty, calls: 4, errors: 1 }], drift: { window_days: 7, version: 2, recent_calls: 3, train_examples: 10, labels: [{ label: "good", train_share: 0.5, recent_share: 1 }], features: [{ feature: "polite", train_mean: 0.4, recent_mean: 0.9, shift: 0.5 }] }, disagreements: [] });
  render(<EvalMonitoring id="eval" />);
  expect(await screen.findByText("needs feedback")).toBeVisible();
  expect(screen.getByText("1 failed")).toBeVisible();
  expect(screen.getByRole("img", { name: "Calls per day" })).toBeVisible();
  expect(screen.getByText(/No feedback yet/)).toBeVisible();
  expect(screen.getByText("polite")).toBeVisible();
  expect(screen.getByText("+0.500")).toBeVisible();
  expect(screen.getByText("No disagreements with feedback in this range.")).toBeVisible();
  expect(api.imMonitoring).toHaveBeenCalledWith("eval", 30);
});

it("shows an empty state before any calls", async () => {
  api.imMonitoring.mockResolvedValue({ days: 30, truncated: false, summary: { ...empty, reliability: [] }, daily: [], versions: [], drift: null, disagreements: [] });
  render(<EvalMonitoring id="eval" />);
  expect(await screen.findByText(/No calls in this range/)).toBeVisible();
});

it("flags a stale rubric and starts improving it", async () => {
  api.imMonitoring.mockResolvedValue({ days: 30, truncated: false, refine_suggested: true, refine_reason: "agreement with feedback fell to 62%", summary: { ...empty, reliability: [] }, daily: [], versions: [], drift: null, disagreements: [] });
  api.imStartRefine.mockResolvedValue({ id: "job", status: "queued" });
  const onImprove = vi.fn();
  render(<EvalMonitoring id="eval" onImprove={onImprove} />);
  expect(await screen.findByText("This rubric may be going stale: agreement with feedback fell to 62%")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Improve rubric" }));
  await waitFor(() => expect(onImprove).toHaveBeenCalled());
  expect(api.imStartRefine).toHaveBeenCalledWith("eval");
});

it("sets an agreement alert", async () => {
  api.imMonitoring.mockResolvedValue({ days: 30, truncated: false, summary: { ...empty, reliability: [] }, daily: [], versions: [], drift: null, disagreements: [] });
  api.imSetAlert.mockResolvedValue({ alert: {} });
  render(<EvalMonitoring id="eval" />);
  fireEvent.change(await screen.findByLabelText("Agreement threshold"), { target: { value: "75" } });
  fireEvent.click(screen.getByRole("button", { name: "Set alert" }));
  await waitFor(() => expect(api.imSetAlert).toHaveBeenCalledWith("eval", { min_agreement: 0.75, channels: ["slack", "email"] }));
});
