import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { RmPlaygroundRun, RmRewardModelDetail } from "@/lib/types";
import ModelPlayground from "./ModelPlayground";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmGetRewardModel: vi.fn(), rmListPlaygroundRuns: vi.fn(), rmGetPlaygroundRun: vi.fn(), rmRunPlayground: vi.fn(), rmGetTrainingExamples: vi.fn() }));
const model = { id: "model", name: "Parts assistant", status: "succeeded", trace_count: 2, trace_ids: ["t1", "t2"], feedback: [], metrics: null } as unknown as RmRewardModelDetail;
const run: RmPlaygroundRun = { id: "r1", reward_model_id: "model", status: "succeeded", input: { prompt: "Find the part", instructions: "Ask first", responses: ["Here is the part", "No"] }, scores: [0, -0.5], error: null, created_at: "2026-10-09T12:00:00Z", started_at: null, finished_at: "2026-10-09T12:00:01Z" };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.rmGetRewardModel).mockResolvedValue(model);
  vi.mocked(api.rmListPlaygroundRuns).mockResolvedValue({ items: [], total: 0 });
  vi.mocked(api.rmRunPlayground).mockResolvedValue(run);
  vi.mocked(api.rmGetPlaygroundRun).mockResolvedValue(run);
  vi.mocked(api.rmGetTrainingExamples).mockResolvedValue({ items: [], total: 0 });
});
async function fill() {
  fireEvent.change(await screen.findByRole("textbox", { name: "Task / user message" }), { target: { value: "Find the part" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Response" }), { target: { value: "Here is the part" } });
}
it("compares actual rewards, preserves zero, and clears stale results when editing", async () => {
  render(<ModelPlayground modelId="model" />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Compare another response" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Response B" }), { target: { value: "No" } });
  fireEvent.click(screen.getByText("System instructions (optional)"));
  fireEvent.change(screen.getByRole("textbox", { name: "System instructions" }), { target: { value: "Ask first" } });
  fireEvent.click(screen.getByRole("button", { name: "Compare responses" }));
  expect(await screen.findByText("Model prefers response A")).toBeVisible();
  expect(api.rmRunPlayground).toHaveBeenCalledWith("model", run.input);
  expect(screen.getByText("0.000")).toBeVisible();
  expect(screen.getByText("-0.500")).toBeVisible();
  fireEvent.change(screen.getByRole("textbox", { name: "Response A" }), { target: { value: "Changed" } });
  expect(screen.queryByText("Model prefers response A")).not.toBeInTheDocument();
});
it("disables scoring until the model and inputs are ready", async () => {
  vi.mocked(api.rmGetRewardModel).mockResolvedValue({ ...model, status: "running" });
  render(<ModelPlayground modelId="model" />);
  await fill();
  expect(screen.getByRole("button", { name: "Score response" })).toBeDisabled();
  expect(screen.getByText(/playground will be ready when training finishes/)).toBeVisible();
  expect(api.rmRunPlayground).not.toHaveBeenCalled();
});
it("shows submission errors without losing the draft", async () => {
  vi.mocked(api.rmRunPlayground).mockRejectedValueOnce(new Error("Could not start scoring"));
  render(<ModelPlayground modelId="model" />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Score response" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not start scoring");
  expect(screen.getByRole("textbox", { name: "Task / user message" })).toHaveValue("Find the part");
  expect(screen.getByRole("button", { name: "Score response" })).toBeEnabled();
});
it("polls queued inference and publishes its completed result", async () => {
  vi.mocked(api.rmRunPlayground).mockResolvedValue({ ...run, status: "queued", scores: null });
  render(<ModelPlayground modelId="model" />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Score response" }));
  expect(await screen.findByText("Waiting to score…")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Task / user message" })).toBeDisabled();
  expect(await screen.findByText("Model prefers response A", {}, { timeout: 3000 })).toBeVisible();
  expect(api.rmGetPlaygroundRun).toHaveBeenCalledWith("model", "r1");
});
it("replays frozen training examples by index with their original context", async () => {
  vi.mocked(api.rmGetTrainingExamples).mockResolvedValue({ total: 1, items: [{ index: 0, chosen: "complete chosen context", rejected: "complete rejected context", partition: "eval", source: null, trace_ids: ["t1"] }] });
  vi.mocked(api.rmRunPlayground).mockResolvedValue({ ...run, input: { example_index: 0, texts: ["complete chosen context", "complete rejected context"] } });
  render(<ModelPlayground modelId="model" />);
  fireEvent.click(await screen.findByRole("button", { name: "Training examples" }));
  expect(await screen.findByText("Held out")).toBeVisible();
  expect(screen.getByRole("link", { name: "Source trace" })).toHaveAttribute("href", "/reward-models/traces/t1");
  fireEvent.click(screen.getByRole("button", { name: "Try this pair" }));
  expect(await screen.findByText("Saved example 1 · original context")).toBeVisible();
  expect(api.rmRunPlayground).toHaveBeenCalledWith("model", { example_index: 0 });
  expect(screen.getByText("complete rejected context")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "New input" }));
  expect(screen.getByRole("textbox", { name: "Task / user message" })).toHaveValue("");
});
it("restores history for editing without starting another inference run", async () => {
  vi.mocked(api.rmListPlaygroundRuns).mockResolvedValue({ total: 1, items: [{ ...run, prompt: "Find the part", example_index: null }] });
  render(<ModelPlayground modelId="model" />);
  fireEvent.click(await screen.findByRole("button", { name: "History" }));
  const table = await screen.findByRole("table", { name: "Playground history" });
  fireEvent.click(within(table).getByRole("button", { name: "Find the part" }));
  expect(await screen.findByRole("textbox", { name: "Response B" })).toHaveValue("No");
  expect(screen.getByText("Model prefers response A")).toBeVisible();
  expect(api.rmRunPlayground).not.toHaveBeenCalled();
});
