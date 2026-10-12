import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { rmGetRewardModel, rmListTraces } from "@/lib/api";
import type { RmRewardModelDetail } from "@/lib/types";
import ModelPlayground from "./ModelPlayground";

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmGetRewardModel: vi.fn(), rmListTraces: vi.fn() }));
const model = { id: "model", name: "Parts assistant", status: "succeeded", trace_count: 2, trace_ids: ["t1", "t2"], metrics: { action_scoring_version: 1 } } as unknown as RmRewardModelDetail;
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(rmListTraces).mockResolvedValue({ traces: [], total: 0 });
  vi.mocked(rmGetRewardModel).mockResolvedValue(model);
});
it("opens the actual selected model directly on the compact trace selector", async () => {
  render(<ModelPlayground modelId="model" />);
  expect(await screen.findByRole("heading", { name: "Parts assistant" })).toBeVisible();
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Trace options" })).toBeVisible();
  expect(screen.getByText("Connect").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByRole("navigation", { name: "Model views" })).not.toBeInTheDocument();
  for (const name of ["Playground", "History", "Training examples"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Response" })).not.toBeInTheDocument();
  expect(rmGetRewardModel).toHaveBeenCalledWith("model");
  expect(screen.getByRole("link", { name: "2 training traces" })).toHaveAttribute("href", "/reward-models?selected=t1,t2");
});
it("recovers from missing model data through Try again", async () => {
  vi.mocked(rmGetRewardModel).mockRejectedValueOnce(new Error("Missing model"));
  render(<ModelPlayground modelId="model" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Missing model");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("heading", { name: "Parts assistant" })).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("keeps the trace selector available while training is incomplete", async () => {
  vi.mocked(rmGetRewardModel).mockResolvedValue({ ...model, status: "running", metrics: null });
  render(<ModelPlayground modelId="model" />);
  expect(await screen.findByText("Training hasn’t finished yet.")).toBeVisible();
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
});
