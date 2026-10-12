import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { RmRewardModelDetail, RmTraceDetail } from "@/lib/types";
import CustomModelTraceSandbox from "./CustomModelTraceSandbox";
vi.mock("@/lib/api", () => ({ rmCreateAnnotation: vi.fn(), rmUpdateAnnotation: vi.fn(), rmGetTrace: vi.fn(), rmListTraces: vi.fn(), rmImportTraces: vi.fn(), rmScoreTrace: vi.fn() }));
const model = { id: "custom", name: "Parts accuracy", status: "succeeded", trace_ids: ["t1"], metrics: { action_scoring_version: 1, trace_scoring_version: 1 } } as unknown as RmRewardModelDetail;
const trace = { id: "t1", title: "Truck task", steps: [{ id: "s1", index: 0, role: "assistant", content: "Here is the part", tool_name: null, tool_input: null }], annotations: [], scores: [{ reward_model_id: "other", score: 99 }, { reward_model_id: "custom", score: 0 }], action_scores: [{ reward_model_id: "other", step_id: "s1", score: 99, credit: 1 }, { reward_model_id: "custom", step_id: "s1", score: 0.5, credit: 0.2 }], scoring_runs: [] } as unknown as RmTraceDetail;
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.rmListTraces).mockResolvedValue({ traces: [{ ...trace, can_score: true }, { ...trace, id: "shared", title: "Shared trace", can_score: false }], total: 2 });
  vi.mocked(api.rmGetTrace).mockResolvedValue(trace);
  vi.mocked(api.rmScoreTrace).mockResolvedValue({ id: "run", trace_id: "t1", reward_model_id: "custom", status: "queued", error: null });
});
it("runs the selected custom model and never displays another model’s scores", async () => {
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Truck task · training trace" }));
  expect(await screen.findByText("Overall reward: 0.000")).toBeVisible();
  expect(screen.getByText("Reward 0.500 · credit 0.200")).toBeVisible();
  expect(screen.queryByText(/99/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Shared trace" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run this model" }));
  expect(await screen.findByText("Queued for scoring with Parts accuracy…")).toBeVisible();
  expect(api.rmScoreTrace).toHaveBeenCalledWith("t1", "custom");
  expect(screen.queryByText("Overall reward: 0.000")).not.toBeInTheDocument();
});
it("persists a human correction without claiming to retrain the current model", async () => {
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Truck task · training trace" }));
  const step = (await screen.findByText("Here is the part")).closest("article")!;
  fireEvent.click(within(step).getByRole("button", { name: "Bad" }));
  expect(await screen.findByText(/Human correction saved/)).toBeVisible();
  expect(api.rmCreateAnnotation).toHaveBeenCalledWith("t1", { step_id: "s1", rating: -1 });
});
it("uploads through the trace importer and selects the returned trace", async () => {
  vi.mocked(api.rmImportTraces).mockResolvedValue({ trace_ids: ["t1"], imported: 1, format: "stash" });
  render(<CustomModelTraceSandbox model={model} />);
  const file = new File(['payload'], 'trace.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => 'payload' });
  fireEvent.change(screen.getByLabelText("Upload sandbox trace"), { target: { files: [file] } });
  expect(await screen.findByText("Trace uploaded and saved to Traces.")).toBeVisible();
  expect(api.rmImportTraces).toHaveBeenCalledWith("auto", "payload");
  expect(api.rmGetTrace).toHaveBeenCalledWith("t1");
});
it("keeps run disabled when a checkpoint is not ready or lacks trace scoring", async () => {
  render(<CustomModelTraceSandbox model={{ ...model, metrics: null }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Truck task · training trace" }));
  expect(await screen.findByRole("button", { name: "Run this model" })).toBeDisabled();
  expect(screen.getByText(/checkpoint does not support trace scoring/)).toBeVisible();
});

it("refreshes a completed run and displays its new scores", async () => {
  vi.mocked(api.rmGetTrace).mockResolvedValueOnce(trace).mockResolvedValue({ ...trace,
    scores: [{ reward_model_id: "custom", reward_model_name: model.name, score: 0.8, created_at: "2026-10-12T00:00:00Z" }],
    scoring_runs: [{ id: "run", trace_id: "t1", reward_model_id: "custom", status: "succeeded", error: null }],
  });
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Truck task · training trace" }));
  fireEvent.click(await screen.findByRole("button", { name: "Run this model" }));
  expect(await screen.findByText("Overall reward: 0.800", {}, { timeout: 3500 })).toBeVisible();
  expect(screen.getByRole("button", { name: "Run this model" })).toBeEnabled();
});
