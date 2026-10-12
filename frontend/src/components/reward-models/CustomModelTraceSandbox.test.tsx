import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import type { RmRewardModelDetail, RmTraceDetail } from "@/lib/types";
import CustomModelTraceSandbox from "./CustomModelTraceSandbox";
vi.mock("@/lib/api", () => ({ rmCreateAnnotation: vi.fn(), rmUpdateAnnotation: vi.fn(), rmGetTrace: vi.fn(), rmListTraces: vi.fn(), rmImportTraces: vi.fn(), rmScoreTrace: vi.fn() }));
const model = { id: "custom", name: "Parts accuracy", status: "succeeded", trace_ids: ["t1"], metrics: { action_scoring_version: 1, trace_scoring_version: 1 } } as unknown as RmRewardModelDetail;
const trace = { id: "t1", title: "Truck task", steps: [{ id: "u1", index: 0, role: "user", content: "Find the part", tool_name: null, tool_input: null }, { id: "s1", index: 1, role: "assistant", content: "Here is the part", tool_name: null, tool_input: null }, { id: "tool1", index: 2, role: "tool", content: "Catalog result", tool_name: "lookup", tool_input: null }], annotations: [], scores: [{ reward_model_id: "other", score: 99 }, { reward_model_id: "custom", score: 0 }], action_scores: [{ reward_model_id: "other", step_id: "s1", score: 99, credit: 1 }, { reward_model_id: "custom", step_id: "s1", score: 0.5, credit: 0.2 }], scoring_runs: [] } as unknown as RmTraceDetail;
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.mocked(api.rmListTraces).mockResolvedValue({ traces: [{ ...trace, can_score: true }, { ...trace, id: "shared", title: "Shared trace", can_score: false }], total: 2 });
  vi.mocked(api.rmGetTrace).mockResolvedValue(trace);
  vi.mocked(api.rmScoreTrace).mockResolvedValue({ id: "run", trace_id: "t1", reward_model_id: "custom", status: "queued", error: null });
});
afterEach(() => vi.unstubAllGlobals());
it("selects a row first and previews the conversation on the right and adds grades after Run", async () => {
  const other = { ...trace, id: "t2", title: "Another trace", steps: [] };
  vi.mocked(api.rmListTraces).mockResolvedValue({ traces: [{ ...trace, can_score: true }, { ...other, can_score: true }, { ...trace, id: "shared", title: "Shared trace", can_score: false }], total: 3 });
  vi.mocked(api.rmGetTrace).mockImplementation(async (id) => id === "t2" ? other : trace);
  vi.mocked(api.rmScoreTrace).mockResolvedValue({ id: "run", trace_id: "t1", reward_model_id: "custom", status: "succeeded", error: null });
  render(<CustomModelTraceSandbox model={model} />);
  const choose = await screen.findByRole("button", { name: "Choose Truck task" });
  fireEvent.click(choose);
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  expect(choose).toHaveAttribute("aria-pressed", "true");
  const input = screen.getByRole("region", { name: "Model input" });
  const output = screen.getByRole("region", { name: "Model output" });
  expect(within(input).getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(within(input).queryByText("Here is the part")).not.toBeInTheDocument();
  expect(within(output).getByText("Here is the part")).toBeVisible();
  expect(within(output).queryByLabelText("Action credit +0.20")).not.toBeInTheDocument();
  expect(api.rmScoreTrace).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Choose Shared trace" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(await within(output).findByText("0.000")).toBeVisible();
  expect(within(output).getByText("Find the part")).toBeVisible();
  expect(within(output).getByText("Here is the part")).toBeVisible();
  expect(within(output).getByText("Catalog result")).toBeVisible();
  expect(within(output).getByLabelText("Action credit +0.20")).toBeVisible();
  expect(within(input).queryByText("Here is the part")).not.toBeInTheDocument();
  expect(screen.queryByText(/99/)).not.toBeInTheDocument();
  expect(api.rmScoreTrace).toHaveBeenCalledWith("t1", "custom");
  fireEvent.click(screen.getByRole("button", { name: "Choose Another trace" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Choose Another trace" })).toHaveAttribute("aria-pressed", "true"));
  expect(within(output).queryByText("Here is the part")).not.toBeInTheDocument();
  expect(within(output).queryByText("0.000")).not.toBeInTheDocument();
  expect(api.rmScoreTrace).toHaveBeenCalledTimes(1);
});
it("persists a human correction without claiming to retrain the current model", async () => {
  vi.mocked(api.rmScoreTrace).mockResolvedValue({ id: "run", trace_id: "t1", reward_model_id: "custom", status: "succeeded", error: null });
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose Truck task" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  const step = (await within(screen.getByRole("region", { name: "Model output" })).findByText("Here is the part")).closest<HTMLElement>("[data-step-id]")!;
  fireEvent.click(within(step).getByRole("button", { name: "Expand assistant message" }));
  await within(step).findByRole("button", { name: "Bad" });
  fireEvent.click(within(step).getByRole("button", { name: "Bad" }));
  expect(await screen.findByText(/Human correction saved/)).toBeVisible();
  expect(api.rmCreateAnnotation).toHaveBeenCalledWith("t1", { step_id: "s1", rating: -1 });
});
it("uploads through the trace importer and selects the returned trace", async () => {
  vi.mocked(api.rmImportTraces).mockResolvedValue({ trace_ids: ["t1"], imported: 1, format: "stash" });
  render(<CustomModelTraceSandbox model={model} />);
  const file = new File(['payload'], 'trace.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => 'payload' });
  fireEvent.change(screen.getByLabelText("Upload trace"), { target: { files: [file] } });
  expect(await screen.findByText("Trace uploaded and saved to Traces.")).toBeVisible();
  expect(api.rmImportTraces).toHaveBeenCalledWith("auto", "payload");
  expect(api.rmGetTrace).toHaveBeenCalledWith("t1");
});
it("keeps run disabled when a checkpoint is not ready or lacks trace scoring", async () => {
  render(<CustomModelTraceSandbox model={{ ...model, metrics: null }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose Truck task" }));
  expect(await screen.findByRole("button", { name: "Run" })).toBeDisabled();
  expect(screen.getByText(/checkpoint does not support trace scoring/)).toBeVisible();
});

it("refreshes a completed run and displays its new scores", async () => {
  vi.mocked(api.rmGetTrace).mockResolvedValueOnce(trace).mockResolvedValue({ ...trace,
    scores: [{ reward_model_id: "custom", reward_model_name: model.name, score: 0.8, created_at: "2026-10-12T00:00:00Z" }],
    scoring_runs: [{ id: "run", trace_id: "t1", reward_model_id: "custom", status: "succeeded", error: null }],
  });
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose Truck task" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(await screen.findByText("Queued for scoring with Parts accuracy…")).toBeVisible();
  expect(screen.getByText("Here is the part")).toBeVisible();
  expect(screen.queryByText("0.000")).not.toBeInTheDocument();
  expect(await screen.findByText("0.800", {}, { timeout: 3500 })).toBeVisible();
  expect(screen.getByRole("button", { name: "Run" })).toBeEnabled();
});

it("disables Run while another row loads so the previous trace cannot be submitted", async () => {
  const second = { ...trace, id: "t2", title: "Another trace" };
  vi.mocked(api.rmListTraces).mockResolvedValue({ traces: [{ ...trace, can_score: true }, { ...second, can_score: true }], total: 2 });
  let resolve!: (value: RmTraceDetail) => void;
  vi.mocked(api.rmGetTrace).mockResolvedValueOnce(trace).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
  render(<CustomModelTraceSandbox model={model} />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose Truck task" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Choose Another trace" }));
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  expect(api.rmScoreTrace).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Choose Another trace" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByText("Here is the part")).not.toBeInTheDocument();
  await act(async () => { resolve(second); });
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  expect(screen.getByRole("button", { name: "Choose Another trace" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "Choose Truck task" })).toHaveAttribute("aria-pressed", "false");
});
