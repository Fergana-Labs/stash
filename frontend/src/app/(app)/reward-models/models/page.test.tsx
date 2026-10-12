import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { rmGetRewardModel, rmListRewardModels } from "@/lib/api";
import { imList } from "@/lib/intuition-api";
import type { RmRewardModel } from "@/lib/types";
import RewardModelsPage from "./page";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/components/reward-models/TrainSheet", () => ({ default: ({ open, onTrained }: { open: boolean; onTrained: (model: { id: string }) => void }) => open ? <button onClick={() => onTrained({ id: "new-custom" })}>Queue test model</button> : null }));
vi.mock("@/components/reward-models/FeedbackDialog", () => ({ default: () => null }));
vi.mock("@/components/reward-models/ViewSkillButton", () => ({ default: () => null }));
vi.mock("@/lib/api", () => ({ rmListRewardModels: vi.fn(), rmGetRewardModel: vi.fn() }));

vi.mock("@/lib/intuition-api", () => ({ imList: vi.fn(), imLoadExample: vi.fn() }));
vi.mock("@/components/intuitions/CreateModelDialog", () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(imList).mockResolvedValue({ models: [], judge: { provider: "jev", configured: true, model: "jev" } });
});
afterEach(() => window.history.replaceState(null, "", "/"));

const ready: RmRewardModel = {
  id: "ready", name: "Coding quality", base_model: "Qwen/Qwen3-0.6B", compute: "modal", epochs: 1,
  status: "succeeded", num_pairs: 20, trace_count: 4, error: null,
  created_at: "2026-10-08T12:34:56Z", started_at: null, finished_at: null,
  metrics: { train_pairs: 16, eval_pairs: 4, eval_accuracy: 0, final_loss: 0.2, epochs: 1, device: "cuda", seconds: 65 },
};
const queued: RmRewardModel = { ...ready, id: "queued", name: "Browser tasks", status: "queued", metrics: null, created_at: "2026-10-09T12:00:00Z" };

it("replaces failed loading with an error and lets the user recover without reloading", async () => {
  vi.mocked(rmListRewardModels)
    .mockRejectedValueOnce(new Error("Internal server error"))
    .mockResolvedValueOnce([{
      id: "model", name: "My reward model", status: "failed", trace_count: 13,
      created_at: new Date().toISOString(), base_model: "Qwen/Qwen3-0.6B",
      compute: "modal", epochs: 1, metrics: null, error: null,
    } as RmRewardModel]);

  render(<RewardModelsPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByText("No reward models yet")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("My reward model")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(rmListRewardModels).toHaveBeenCalledTimes(2);
});

it("keeps the table headers visible in the empty state", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  render(<RewardModelsPage />);
  await screen.findByText("No reward models yet");
  expect(screen.getAllByRole("columnheader").map((el) => el.textContent)).toEqual(["Model", "Status", "Est. remaining", "Model type / base", "Examples / traces", "Eval accuracy", "Created"]);
  expect(screen.getByRole("button", { name: "New model" })).toBeVisible();
});

it("searches names and base models, filters status, and sorts rows", async () => {
  const user = userEvent.setup();
  vi.mocked(rmListRewardModels).mockResolvedValue([ready, queued]);
  render(<RewardModelsPage />);
  await screen.findByRole("link", { name: ready.name });
  const names = () => screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("link").textContent);
  expect(names()).toEqual([queued.name, ready.name]);
  await user.click(screen.getByRole("button", { name: "Created" }));
  expect(names()).toEqual([ready.name, queued.name]);
  await user.click(screen.getByRole("button", { name: "Model" }));
  expect(names()).toEqual([queued.name, ready.name]);

  const search = screen.getByRole("textbox", { name: "Search models" });
  await user.type(search, "coding");
  expect(names()).toEqual([ready.name]);
  await user.clear(search);
  await user.type(search, "Qwen3");
  expect(names()).toHaveLength(2);
  await user.click(screen.getByRole("combobox", { name: "Filter model status" }));
  await user.click(screen.getByRole("option", { name: "Ready" }));
  expect(names()).toEqual([ready.name]);
  await user.clear(search);
  await user.type(search, "missing");
  expect(screen.getByText("No matching models")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(names()).toHaveLength(2);
});

it("expands from a model link, preserves zero accuracy, and opens the source traces", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready, queued]);
  vi.mocked(rmGetRewardModel).mockResolvedValue({ ...ready, trace_ids: ["t1", "t2"], feedback: [] });
  window.history.replaceState(null, "", "#model-ready");
  render(<RewardModelsPage />);
  const details = await screen.findByRole("region", { name: `${ready.name} details` });
  expect(within(details).getByText("0.0%")).toBeVisible();
  expect(within(details).getByText("16 + 4")).toBeVisible();
  expect(within(details).getByRole("button", { name: "Download weights" })).toBeVisible();
  const time = document.querySelector("time");
  expect(time).toHaveAttribute("datetime", queued.created_at);
  expect(time).toHaveAttribute("title");
  fireEvent.click(within(details).getByRole("button", { name: "Trained on 4 traces" }));
  await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/reward-models?selected=t1,t2"));
  fireEvent.click(screen.getByRole("button", { name: `${ready.name} details` }));
  expect(screen.queryByRole("region", { name: `${ready.name} details` })).not.toBeInTheDocument();
});

it("shows a failed model’s log when its row is expanded", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([{ ...ready, status: "failed", metrics: null, error: "Worker log\nTraining failed: no usable pairs" }]);
  render(<RewardModelsPage />);
  fireEvent.click(await screen.findByRole("button", { name: `${ready.name} details` }));
  expect(screen.getByText("Training failed: no usable pairs")).toBeVisible();
  expect(screen.getByText("Show log")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Download weights" })).not.toBeInTheDocument();
});


it("opens the model playground from the model name", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  render(<RewardModelsPage />);
  expect(await screen.findByRole("link", { name: ready.name })).toHaveAttribute("href", "/reward-models/models/ready");
});


it("lists rubric-based models alongside trained models and opens their sandbox", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  vi.mocked(imList).mockResolvedValue({
    judge: { provider: "jev", configured: true, model: "jev" },
    models: [{ id: "support", name: "Support reply", output_type: "choice", active_version_id: null,
      draft_version_id: "draft", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z",
      active_number: null, active_metrics: null, active_description: null, draft_description: "Support rubric",
      examples: 12, inbox: 3 }],
  });
  render(<RewardModelsPage />);
  expect(await screen.findByRole("link", { name: "Support reply" })).toHaveAttribute("href", "/reward-models/models/sandbox/support");
  expect(screen.getByRole("link", { name: ready.name })).toBeVisible();
  expect(screen.getByText("2 models")).toBeVisible();
  await userEvent.setup().click(screen.getByText("More options"));
  expect(screen.getByRole("button", { name: "Load example" })).toBeVisible();
  const toggle = screen.getByRole("button", { name: "Support reply details" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await userEvent.setup().click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const details = screen.getByRole("region", { name: "Support reply details" });
  expect(within(details).getByRole("link", { name: "Open playground" })).toHaveAttribute("href", "/reward-models/models/sandbox/support?tab=playground");
  expect(within(details).getByRole("link", { name: "3 predictions to review" })).toHaveAttribute("href", "/reward-models/models/sandbox/support?tab=inbox");
  await userEvent.setup().click(toggle);
  expect(screen.queryByRole("region", { name: "Support reply details" })).not.toBeInTheDocument();
  await userEvent.setup().type(screen.getByRole("textbox", { name: "Search models" }), "Rubric-based");
  expect(screen.getByRole("link", { name: "Support reply" })).toBeVisible();
  expect(screen.queryByRole("link", { name: ready.name })).not.toBeInTheDocument();
});

it("creates a trace-trained custom model from New model and opens that model", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  render(<RewardModelsPage />);
  await screen.findByText("No reward models yet");
  await userEvent.setup().click(screen.getByRole("button", { name: "New model" }));
  await userEvent.setup().click(screen.getByRole("button", { name: "Queue test model" }));
  expect(push).toHaveBeenCalledWith("/reward-models/models/new-custom");
});
