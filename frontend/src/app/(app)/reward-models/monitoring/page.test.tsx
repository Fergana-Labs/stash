import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import MonitoringPage from "./page";

const api = vi.hoisted(() => ({ models: vi.fn(), traces: vi.fn(), score: vi.fn(), optimizations: vi.fn(async () => []) }));
vi.mock("@/lib/api", () => ({ rmListRewardModels: api.models, rmListAllTraces: api.traces, rmScoreTrace: api.score }));
vi.mock("@/lib/optimization-api", () => ({ listOptimizations: api.optimizations }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reward-models/monitoring" }));

it("loads the selected model's scores and never substitutes automatic annotations", async () => {
  api.models.mockResolvedValue(["one", "two"].map((id) => ({ id, name: `Model ${id}`, status: "succeeded", metrics: { trace_scoring_version: 1 } })));
  let finishSecond!: (value: unknown[]) => void;
  api.traces.mockImplementation(async (_query, modelId) => modelId === "one" ? [{ id: "trace", title: "Scored trace", agent: "codex", source_format: "codex", created_at: "2026-10-07", evaluation: { current: true, score: 0.87 }, latest_score: { reward_model_id: "one", score: -2 } }] : new Promise((resolve) => { finishSecond = resolve; }));
  render(<MonitoringPage />);
  expect(await screen.findByRole("link", { name: "Scored trace" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "-2.00" })).toBeVisible();
  expect(screen.queryByText("0.87")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("combobox", { name: "Reward model" }));
  fireEvent.click(await screen.findByRole("option", { name: "Model two" }));
  await waitFor(() => expect(api.traces).toHaveBeenCalledWith("", "two"));
  expect(screen.queryByRole("link", { name: "Scored trace" })).not.toBeInTheDocument();
  await act(async () => finishSecond([]));
  expect(screen.getByText("No runs have a saved score from this model yet.")).toBeVisible();
});

it("monitors action-only models using that model's saved action credit", async () => {
  api.models.mockResolvedValue([{ id: "actions", name: "Action model", status: "succeeded", metrics: { action_scoring_version: 1 } }]);
  api.traces.mockResolvedValue([{ id: "trace", title: "Action-scored trace", created_at: "2026-10-07", source_format: "codex", action_credit: { mean: -0.3, count: 4 }, latest_score: null, evaluation: { current: true, score: 0.87 } }]);
  render(<MonitoringPage />);
  expect(await screen.findByRole("link", { name: "Action-scored trace" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "Action credit" })).toBeVisible();
  expect(screen.getByRole("cell", { name: "-0.30" })).toBeVisible();
  expect(screen.queryByText("0.87")).not.toBeInTheDocument();
});

it("shows live prompt experiments for the selected model rather than training jobs", async () => {
  api.models.mockResolvedValue([{ id: "one", name: "Reward model", status: "succeeded", metrics: { trace_scoring_version: 1 } }]);
  api.traces.mockResolvedValue([]);
  api.optimizations.mockResolvedValue([{ id: "experiment", name: "Support prompt", reward_model_id: "one", agent: "support", status: "running", run_count: 12 }, { id: "other", name: "Unrelated experiment", reward_model_id: "two", agent: "support", status: "running", run_count: 5 }] as never);
  render(<MonitoringPage />);
  expect(await screen.findByRole("link", { name: "Support prompt" })).toHaveAttribute("href", "/reward-models/optimization/experiment");
  expect(screen.queryByRole("link", { name: "Unrelated experiment" })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Prompt optimization" })).toHaveAttribute("href", "/reward-models/monitoring#prompt-optimization");
  expect(screen.queryByText("Preparing data")).not.toBeInTheDocument();
});
