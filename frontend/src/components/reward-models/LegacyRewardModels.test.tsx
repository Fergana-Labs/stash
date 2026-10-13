import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { rmGetRewardModel, rmListRewardModels } from "@/lib/api";
import { imList } from "@/lib/intuition-api";
import type { RmRewardModel } from "@/lib/types";
import RewardModelsPage from "./LegacyRewardModels";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/components/reward-models/TrainSheet", () => ({ default: ({ open, onTrained }: { open: boolean; onTrained: (model: { id: string }) => void }) => open ? <button onClick={() => onTrained({ id: "new-custom" })}>Queue test model</button> : null }));
vi.mock("@/lib/api", () => ({ rmListRewardModels: vi.fn(), rmGetRewardModel: vi.fn(), rmListTraces: vi.fn(async () => ({ traces: [], total: 0 })) }));
vi.mock("@/components/intuitions/IntuitionDetail", () => ({ default: ({ id, embedded }: { id: string; embedded?: boolean }) => <p>{embedded ? "Embedded" : "Standalone"} rubric playground for {id}</p> }));

vi.mock("@/lib/intuition-api", () => ({ imList: vi.fn(), imLoadExample: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(rmGetRewardModel).mockResolvedValue({ ...ready, trace_ids: ["t1", "t2"], feedback: [] });
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
  expect(await screen.findByRole("button", { name: "My reward model" })).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(rmListRewardModels).toHaveBeenCalledTimes(2);
});

it("keeps the table headers visible in the empty state", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  render(<RewardModelsPage />);
  await screen.findByText("No reward models yet");
  expect(screen.queryByRole("button", { name: "Create rubric judge" })).not.toBeInTheDocument();
  expect(screen.getAllByRole("columnheader").map((el) => el.textContent)).toEqual(["Model", "Status", "Est. remaining", "Model type / base", "Examples / traces", "Eval accuracy", "Created"]);
  expect(screen.getByRole("button", { name: "New eval" })).toBeVisible();
});

it("searches names and base models, filters status, and sorts rows", async () => {
  const user = userEvent.setup();
  vi.mocked(rmListRewardModels).mockResolvedValue([ready, queued]);
  render(<RewardModelsPage />);
  await screen.findByRole("button", { name: ready.name });
  const names = () => Array.from(document.querySelectorAll("[data-model-row]")).map((row) => within(row as HTMLElement).getAllByRole("button")[1].textContent);
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

it("opens the full inline playground from a model hash and collapses with the chevron", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready, queued]);
  window.history.replaceState(null, "", "#model-ready");
  render(<RewardModelsPage />);
  const details = await screen.findByRole("region", { name: ready.name + " details" });
  expect(await within(details).findByRole("heading", { name: "Input" })).toBeVisible();
  expect(within(details).getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(within(details).getByRole("heading", { name: "Output" })).toBeVisible();
  expect(screen.getByText("0.0%")).toBeVisible();
  expect(within(details).queryByText("16 + 4")).not.toBeInTheDocument();
  expect(within(details).queryByRole("button", { name: "Download weights" })).not.toBeInTheDocument();
  expect(within(details).queryByText(/Trained on/)).not.toBeInTheDocument();
  const time = document.querySelector("time");
  expect(time).toHaveAttribute("datetime", queued.created_at);
  expect(time).toHaveAttribute("title");
  fireEvent.click(screen.getByRole("button", { name: ready.name + " details" }));
  expect(screen.queryByRole("region", { name: ready.name + " details" })).not.toBeInTheDocument();
});

it("shows the failed model state inside the inline playground", async () => {
  const failed = { ...ready, status: "failed" as const, metrics: null, error: "Training failed: no usable pairs" };
  vi.mocked(rmListRewardModels).mockResolvedValue([failed]);
  vi.mocked(rmGetRewardModel).mockResolvedValue({ ...failed, trace_ids: [], feedback: [] });
  render(<RewardModelsPage />);
  fireEvent.click(await screen.findByRole("button", { name: ready.name + " details" }));
  const details = await screen.findByRole("region", { name: ready.name + " details" });
  expect(await within(details).findByText("Training failed: no usable pairs")).toBeVisible();
  expect(within(details).getByRole("button", { name: "Run" })).toBeDisabled();
});

it("toggles the inline playground from the model name without navigating away", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  render(<RewardModelsPage />);
  const name = await screen.findByRole("button", { name: ready.name });
  expect(rmGetRewardModel).not.toHaveBeenCalled();
  expect(name).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(name);
  const details = await screen.findByRole("region", { name: ready.name + " details" });
  expect(await within(details).findByRole("heading", { name: "Input" })).toBeVisible();
  expect(name).toHaveAttribute("aria-expanded", "true");
  expect(rmGetRewardModel).toHaveBeenCalledWith(ready.id);
  expect(push).not.toHaveBeenCalled();
  fireEvent.click(name);
  expect(screen.queryByRole("region", { name: ready.name + " details" })).not.toBeInTheDocument();
  expect(name).toHaveAttribute("aria-expanded", "false");
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
  expect(await screen.findByRole("button", { name: "Support reply" })).toBeVisible();
  expect(screen.getByRole("button", { name: ready.name })).toBeVisible();
  expect(screen.getByText("2 models")).toBeVisible();
  await userEvent.setup().click(screen.getByText("More options"));
  expect(screen.getByRole("menuitem", { name: "Load example" })).toBeVisible();
  const toggle = screen.getByRole("button", { name: "Support reply details" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await userEvent.setup().click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const details = screen.getByRole("region", { name: "Support reply details" });
  expect(within(details).getByText("Embedded rubric playground for support")).toBeVisible();
  expect(within(details).queryByText("Open playground")).not.toBeInTheDocument();
  expect(within(details).queryByRole("link", { name: /predictions to review/ })).not.toBeInTheDocument();
  expect(within(details).queryByRole("link", { name: /labeled examples/ })).not.toBeInTheDocument();
  await userEvent.setup().click(toggle);
  expect(screen.queryByRole("region", { name: "Support reply details" })).not.toBeInTheDocument();
  await userEvent.setup().type(screen.getByRole("textbox", { name: "Search models" }), "Rubric-based");
  expect(screen.getByRole("button", { name: "Support reply" })).toBeVisible();
  expect(screen.queryByRole("button", { name: ready.name })).not.toBeInTheDocument();
});

it("routes new creation to the eval builder instead of trace training", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  render(<RewardModelsPage />);
  await screen.findByText("No reward models yet");
  await userEvent.setup().click(screen.getByRole("button", { name: "New eval" }));
  expect(push).toHaveBeenCalledWith("/reward-models/evals/new");
  expect(screen.queryByRole("button", { name: "Queue test model" })).not.toBeInTheDocument();
});

it("keeps one Connect section below the model table and copies the chosen model", async () => {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  vi.mocked(rmListRewardModels).mockResolvedValue([ready, queued]);
  render(<RewardModelsPage />);
  await user.click(await screen.findByRole("button", { name: ready.name }));
  const details = await screen.findByRole("region", { name: ready.name + " details" });
  await within(details).findByRole("heading", { name: "Input" });
  const connect = screen.getByText("Connect");
  expect(screen.getAllByText("Connect")).toHaveLength(1);
  expect(connect.closest("table")).toBeNull();
  expect(screen.getByRole("table", { name: "Reward models" }).compareDocumentPosition(connect) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await user.click(connect);
  await user.click(screen.getByRole("combobox", { name: "Connect model" }));
  await user.click(screen.getByRole("option", { name: queued.name }));
  await user.click(screen.getByRole("button", { name: "Copy API example" }));
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"reward_model_id": "queued"'));
  await user.click(screen.getByRole("button", { name: ready.name }));
  expect(screen.getByText("Connect")).toBeVisible();
});

it("dismisses More options with Escape and an outside click", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([]);
  const user = userEvent.setup();
  render(<RewardModelsPage />);
  await user.click(screen.getByRole("button", { name: "More options" }));
  expect(await screen.findByRole("menuitem", { name: "Load example" })).toBeVisible();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menuitem", { name: "Load example" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "More options" }));
  await screen.findByRole("menuitem", { name: "Load example" });
  await user.click(screen.getByRole("heading", { name: "Reward models" }));
  expect(screen.queryByRole("menuitem", { name: "Load example" })).not.toBeInTheDocument();
});

it("toggles the playground from any noninteractive cell without double-toggling the name", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  render(<RewardModelsPage />);
  const name = await screen.findByRole("button", { name: ready.name });
  const row = name.closest("tr")!;
  fireEvent.click(within(row).getByText("Ready"));
  expect(await screen.findByRole("region", { name: ready.name + " details" })).toBeVisible();
  fireEvent.click(within(row).getByText("4", { exact: true }));
  expect(screen.queryByRole("region", { name: ready.name + " details" })).not.toBeInTheDocument();
  fireEvent.click(name);
  expect(screen.getByRole("region", { name: ready.name + " details" })).toBeVisible();
});

it("shows model names without waiting for the legacy model request", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  vi.mocked(imList).mockImplementation(() => new Promise(() => {}));
  render(<RewardModelsPage />);
  expect(await screen.findByRole("button", { name: ready.name })).toBeVisible();
  expect(screen.queryByText("Loading reward models…")).not.toBeInTheDocument();
});

it("keeps trained models usable when the legacy request fails", async () => {
  vi.mocked(rmListRewardModels).mockResolvedValue([ready]);
  vi.mocked(imList).mockRejectedValue(new Error("Legacy unavailable"));
  render(<RewardModelsPage />);
  expect(await screen.findByRole("button", { name: ready.name })).toBeVisible();
  expect(await screen.findByRole("alert")).toHaveTextContent("Legacy unavailable");
  fireEvent.click(screen.getByRole("button", { name: ready.name }));
  expect(await screen.findByRole("region", { name: ready.name + " details" })).toBeVisible();
});
