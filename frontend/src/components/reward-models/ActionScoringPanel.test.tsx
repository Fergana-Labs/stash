import type { ReactElement } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { rmListRewardModels, rmScoreTrace, rmSetTrainingContribution } from "@/lib/api";
import type { RmRewardModel, RmScoringRun, RmTraceDetail } from "@/lib/types";
import ActionScoringPanel from "./ActionScoringPanel";
import { actionModelId } from "./action-credit";

vi.mock("@/lib/api", () => ({ rmListRewardModels: vi.fn(), rmScoreTrace: vi.fn(), rmSetTrainingContribution: vi.fn() }));

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

function renderPanel(ui: ReactElement) {
  const result = render(ui);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Action credit" }));
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rmListRewardModels).mockResolvedValue(models);
});
afterEach(() => vi.useRealTimers());

it("keeps personal models in advanced options and requests saved-model inference", async () => {
  const onModelChange = vi.fn(), onReload = vi.fn().mockResolvedValue(undefined);
  vi.mocked(rmScoreTrace).mockResolvedValue({ id: "run" } as RmScoringRun);
  renderPanel(<ActionScoringPanel trace={trace} selectedModelId="model1" onModelChange={onModelChange} onReload={onReload} />);
  fireEvent.click(screen.getByText("Advanced: personal reward models"));
  const selector = await screen.findByRole("combobox", { name: "Action credit model" });
  expect(onModelChange).not.toHaveBeenCalled();
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
  const { rerender } = renderPanel(<ActionScoringPanel {...props} />);
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

it("shows shared bootstrap status without selecting a personal model or contributing data", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([models[1]]);
  const onModelChange = vi.fn();
  renderPanel(<ActionScoringPanel trace={{ ...trace, action_scores: [] }} selectedModelId="default" onModelChange={onModelChange} onReload={vi.fn()} />);
  expect(screen.getByText(/No evaluator is available yet/)).toBeVisible();
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  fireEvent.click(screen.getByText("Advanced: personal reward models"));
  expect(await screen.findByRole("link", { name: "Train a reward model" })).toHaveAttribute("href", "/reward-models");
  expect(screen.queryByRole("button", { name: /Score/ })).not.toBeInTheDocument();
  expect(onModelChange).not.toHaveBeenCalled();
  expect(rmSetTrainingContribution).not.toHaveBeenCalled();
});

it("shows saved action scores automatically before a shared evaluator exists", async () => {
  const onReload = vi.fn().mockResolvedValue(undefined);
  expect(actionModelId(trace, "default")).toBe("model1");
  expect(actionModelId(trace, null)).toBeNull();
  expect(actionModelId(trace, "model2")).toBe("model2");
  const shared = { ...trace, default_evaluator: { id: "shared", name: "Stash", revision: 1, updated_at: "today" } };
  expect(actionModelId(shared, "default")).toBe("shared");
  renderPanel(<ActionScoringPanel trace={trace} selectedModelId="default" onModelChange={vi.fn()} onReload={onReload} />);
  expect(screen.getByText("1 / 2 actions scored")).toBeVisible();
  expect(screen.queryByText(/No evaluator is available/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Score again" }));
  await waitFor(() => expect(rmScoreTrace).toHaveBeenCalledWith("trace", "model1"));
});

it("uses the shared default without requiring personal training and explicitly saves contribution permission", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  vi.mocked(rmSetTrainingContribution).mockResolvedValue(undefined);
  const onReload = vi.fn().mockResolvedValue(undefined);
  const shared = { ...trace, default_evaluator: { id: "model1", name: "Stash", revision: 3, updated_at: "today" } };
  renderPanel(<ActionScoringPanel trace={shared} selectedModelId="default" onModelChange={vi.fn()} onReload={onReload} />);
  expect(screen.getByText("Stash evaluator · v3")).toBeVisible();
  expect(screen.getByText("1 / 2 actions scored")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Score again" }));
  await waitFor(() => expect(rmScoreTrace).toHaveBeenCalledWith("trace", undefined));
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() => expect(rmSetTrainingContribution).toHaveBeenCalledWith("trace", true));
  await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));
});

it("polls automatic scoring before a run starts, then stops after bounded failures", async () => {
  const onReload = vi.fn().mockResolvedValue(undefined);
  const shared = { ...trace, default_evaluator: { id: "model1", name: "Stash", revision: 1, updated_at: "today" }, automatic_scoring: { attempts: 0, error: null } };
  const props = { trace: shared, selectedModelId: "default", onModelChange: vi.fn(), onReload };
  const { rerender } = renderPanel(<ActionScoringPanel {...props} />);
  await waitFor(() => expect(rmListRewardModels).toHaveBeenCalled());
  vi.useFakeTimers();
  // Recreate the timer under the fake clock.
  rerender(<ActionScoringPanel {...props} trace={{ ...shared, automatic_scoring: null }} />);
  rerender(<ActionScoringPanel {...props} />);
  expect(screen.getByText("Automatic scoring is queued.")).toBeVisible();
  await act(() => vi.advanceTimersByTimeAsync(3000));
  expect(onReload).toHaveBeenCalledTimes(1);
  rerender(<ActionScoringPanel {...props} trace={{ ...shared, automatic_scoring: { attempts: 3, error: null } }} />);
  await act(() => vi.advanceTimersByTimeAsync(6000));
  expect(onReload).toHaveBeenCalledTimes(1);
});
