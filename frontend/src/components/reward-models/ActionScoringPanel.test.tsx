import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { rmListRewardModels, rmScoreTrace } from "@/lib/api";
import type { RmRewardModel, RmScoringRun, RmTraceDetail } from "@/lib/types";
import ActionScoringPanel from "./ActionScoringPanel";

vi.mock("@/lib/api", () => ({ rmListRewardModels: vi.fn(), rmScoreTrace: vi.fn() }));

const models = [
  { id: "model1", name: "Parts evaluator", status: "succeeded", metrics: { action_scoring_version: 1 } },
  { id: "legacy", name: "Old model", status: "succeeded", metrics: {} },
  { id: "model2", name: "Second evaluator", status: "succeeded", metrics: { action_scoring_version: 1 } },
] as RmRewardModel[];
const trace = {
  id: "trace", steps: [
    { id: "user", role: "user", content: "Find a part" },
    { id: "call", role: "assistant", content: "", tool_name: "lookup" },
    { id: "result", role: "tool", content: "Found", tool_name: "lookup" },
    { id: "response", role: "assistant", content: "Here it is" },
  ], action_scores: [{ reward_model_id: "model1", step_id: "call", credit: 0.4 }], scoring_runs: [],
} as unknown as RmTraceDetail;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rmListRewardModels).mockResolvedValue(models);
});
afterEach(() => vi.useRealTimers());

it("selects an eligible model, counts only actions, and requests saved-model inference", async () => {
  const onModelChange = vi.fn(), onReload = vi.fn().mockResolvedValue(undefined);
  vi.mocked(rmScoreTrace).mockResolvedValue({ id: "run" } as RmScoringRun);
  render(<ActionScoringPanel trace={trace} selectedModelId="model1" onModelChange={onModelChange} onReload={onReload} />);
  const selector = await screen.findByRole("combobox", { name: "Action credit model" });
  expect(onModelChange).toHaveBeenCalledWith("model1");
  expect(screen.queryByRole("option", { name: "Old model" })).not.toBeInTheDocument();
  expect(screen.getByText("1 / 2 actions scored")).toBeVisible();
  fireEvent.change(selector, { target: { value: "model2" } });
  expect(onModelChange).toHaveBeenCalledWith("model2");
  fireEvent.click(screen.getByRole("button", { name: "Score again" }));
  await waitFor(() => expect(rmScoreTrace).toHaveBeenCalledWith("trace", "model1"));
  expect(onReload).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/not correctness probabilities/)).toBeVisible();
});

it("polls only while the selected model's job is active and shows failures", async () => {
  const onReload = vi.fn().mockResolvedValue(undefined), onModelChange = vi.fn();
  const props = { trace, selectedModelId: "model1", onModelChange, onReload };
  const { rerender } = render(<ActionScoringPanel {...props} />);
  await screen.findByRole("button", { name: "Score again" });
  vi.useFakeTimers();
  const active = { ...trace, scoring_runs: [{ id: "run", reward_model_id: "model1", status: "running" } as RmScoringRun] };
  rerender(<ActionScoringPanel {...props} trace={active} />);
  expect(screen.getByRole("button", { name: "Scoring…" })).toBeDisabled();
  await act(() => vi.advanceTimersByTimeAsync(3000));
  expect(onReload).toHaveBeenCalledTimes(1);
  const failed = { ...trace, scoring_runs: [{ ...active.scoring_runs[0], status: "failed", error: "Worker unavailable" } as RmScoringRun] };
  rerender(<ActionScoringPanel {...props} trace={failed} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Worker unavailable");
  await act(() => vi.advanceTimersByTimeAsync(6000));
  expect(onReload).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Score again" })).toBeEnabled();
});

it("explains that legacy models require new training", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([models[1]]);
  render(<ActionScoringPanel trace={trace} selectedModelId={null} onModelChange={vi.fn()} onReload={vi.fn()} />);
  expect(await screen.findByRole("link", { name: "Train a reward model" })).toHaveAttribute("href", "/reward-models");
  expect(screen.queryByRole("button", { name: /Score/ })).not.toBeInTheDocument();
});
