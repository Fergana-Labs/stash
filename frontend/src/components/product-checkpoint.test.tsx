import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ProductCheckpointProvider } from "./ProductCheckpointContext";
import RewardRail from "./workspace/reward-rail";
import TraceTable from "./reward-models/TraceTable";
import TrainPanel from "./reward-models/TrainPanel";
import type { ProductCheckpoint, RmTraceSummary, User } from "@/lib/types";

const api = vi.hoisted(() => ({ create: vi.fn(), list: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/reward-models",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: api.push }),
}));
vi.mock("@/lib/api", () => ({ rmCreateRewardModel: api.create, rmListRewardModels: api.list }));
vi.mock("./workspace/account-menu", () => ({ default: () => <div>Account</div> }));

const user: User = {
  id: "sam", name: "sam", display_name: "Sam", email: "sam@ferganalabs.com",
  developer_platform_only: false, reward_models_enabled: true,
  description: "", created_at: "2026-10-05", last_seen: "2026-10-05",
};
const trace: RmTraceSummary = {
  id: "heavi", title: "Heavi production trace", external_id: "heavi-production:one", source_format: "stash",
  step_count: 10, comment_count: 1, positive_count: 0, negative_count: 0, label_error_count: 0,
  latest_score: null, created_at: "2026-10-05T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  // The current reward navigation includes the system-theme toggle.
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  api.list.mockResolvedValue([]);
  api.create.mockResolvedValue({ id: "new-model" });
});
afterEach(() => { vi.unstubAllGlobals(); delete document.documentElement.dataset.theme; });

it.each<ProductCheckpoint>(["latest", "floodgate-2026-10-05"])("selects the account's navigation: %s", (checkpoint) => {
  render(<RewardRail user={{ ...user, product_checkpoint: checkpoint }} onLogout={vi.fn()} />);
  expect(screen.getByRole("link", { name: "Traces" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Reward models" })).toBeVisible();
  if (checkpoint === "latest") {
    expect(screen.getByRole("link", { name: "Monitoring" })).toBeVisible();
    for (const name of ["Skills", "Review", "Changes", "Optimization"]) expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
  } else {
    expect(screen.getByRole("link", { name: "Skills" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Changes" })).not.toBeInTheDocument();
  }
});

it.each<ProductCheckpoint>(["latest", "floodgate-2026-10-05"])("shows the checkpoint's trace columns while retaining owned traces: %s", (checkpoint) => {
  render(<ProductCheckpointProvider checkpoint={checkpoint}>
    <TraceTable traces={[trace]} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />
  </ProductCheckpointProvider>);
  expect(screen.getByRole("link", { name: "Heavi production trace" })).toBeVisible();
  expect(screen.queryByRole("columnheader", { name: "Trace score" }) !== null).toBe(checkpoint === "latest");
  expect(screen.queryByRole("columnheader", { name: "Source" }) !== null).toBe(checkpoint === "latest");
  expect(screen.queryByRole("combobox", { name: "Filter traces" }) !== null).toBe(checkpoint === "latest");
  expect(screen.queryByRole("button", { name: "Mean action credit" }) !== null).toBe(checkpoint !== "latest");
});

it("restores the original single-trace training payload without the new rubric configuration", async () => {
  render(<ProductCheckpointProvider checkpoint="floodgate-2026-10-05">
    <TrainPanel traceIds={[trace.id]} summary={{ count: 1 }} optionsPlacement="below" onTrained={vi.fn()} />
  </ProductCheckpointProvider>);
  await waitFor(() => expect(api.list).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Options" }));
  expect(screen.queryByRole("textbox", { name: "Reward criteria" })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("reward-model-1"));
  fireEvent.click(screen.getByRole("button", { name: "Create new reward model" }));
  await waitFor(() => expect(api.create).toHaveBeenCalledWith({ trace_ids: [trace.id], name: "reward-model-1", base_model: "Qwen/Qwen3-0.6B", epochs: 1 }));
});

it("keeps current training constraints for other accounts", async () => {
  render(<TrainPanel traceIds={[trace.id]} summary={{ count: 1 }} optionsPlacement="below" onTrained={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Create new reward model" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "Model name" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Options" })).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Reward criteria" })).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "Base model" })).not.toBeInTheDocument();
  expect(screen.queryByRole("spinbutton", { name: "Epochs" })).not.toBeInTheDocument();
  expect(api.list).not.toHaveBeenCalled();
});

it("accepts a name inline and uses automatic training without client-side hyperparameters", async () => {
  render(<TrainPanel traceIds={["one", "two"]} summary={{ count: 2 }} optionsPlacement="below" onTrained={vi.fn()} />);
  const create = screen.getByRole("button", { name: "Create new reward model" });
  expect(create).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Model name" }), { target: { value: " Parts quality " } });
  fireEvent.click(create);
  await waitFor(() => expect(api.create).toHaveBeenCalledWith({
    trace_ids: ["one", "two"], name: "Parts quality",
    training_config: { input_version: 3, annotation_source: "automatic" },
  }));
});
