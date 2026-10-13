import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import MonitoringPage from "./page";
import type { MonitoringOverview, RewardHistory } from "@/lib/monitoring-api";

const api = vi.hoisted(() => ({ overview: vi.fn(), history: vi.fn(), detail: vi.fn(), gepa: vi.fn() }));
vi.mock("@/lib/monitoring-api", () => ({ getMonitoring: api.overview, getRewardHistory: api.history }));
vi.mock("@/lib/optimization-api", () => ({ getOptimization: api.detail }));
vi.mock("@/lib/api", () => ({ rmGetGepaRun: api.gepa }));
vi.mock("@/components/optimization/CreateOptimization", () => ({ default: ({ initialAgent }: { initialAgent: string }) => <p>Begin optimization for {initialAgent}</p> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/reward-models/monitoring" }));

const overview: MonitoringOverview = {
  agents: [{ agent: "codex", display_name: "Codex", trace_count: 60, last_seen: "2026-10-12" }, { agent: "support", display_name: "Support", trace_count: 10, last_seen: "2026-10-11" }],
  models: [{ id: "one", name: "Model one", metrics: { action_scoring_version: 1 }, finished_at: "2026-10-10" }, { id: "two", name: "Model two", metrics: { action_scoring_version: 1 }, finished_at: "2026-10-10" }], programs: [], gepa: [],
};
const history: RewardHistory = { agent: "codex", model_id: "one", program_id: null, active_revision_id: null, unit: "action_credit", window: 20, total: 60, mean: 0.2, current_n: 20, current_mean: 0.4, previous_n: 20, previous_mean: 0.1, points: [{ id: "trace", trace_id: "trace", title: "Recorded task", recorded_at: "2026-10-10", reward: 0.5, revision_id: null, rolling_mean: 0.4, window_count: 20 }] };

beforeEach(() => { vi.clearAllMocks(); api.overview.mockResolvedValue(overview); api.history.mockResolvedValue(history); });

it("starts with agents, shows reward units and does not imply an accepted prompt", async () => {
  render(<MonitoringPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Codex" }));
  expect(await screen.findByText("+0.300")).toBeVisible();
  expect(screen.getByRole("button", { name: "Codex" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("No prompt optimization is connected to this agent yet.")).toBeVisible();
  expect(screen.getByText("Not tracked")).toBeVisible();
  expect(screen.getByText("No GEPA trials recorded yet.")).toBeVisible();
  expect(api.history).toHaveBeenCalledWith("codex", "one", 20, undefined);
  fireEvent.click(screen.getByRole("button", { name: "Optimize prompt" }));
  expect(screen.getByText("Begin optimization for codex")).toBeVisible();
});

it("selects an agent anywhere on its row and clears stale rewards immediately", async () => {
  let finish!: (data: RewardHistory) => void;
  api.history.mockImplementation(async (agent, model) => agent === "codex" && model === "one" ? history : new Promise((resolve) => { finish = resolve; }));
  render(<MonitoringPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Codex" }));
  expect(await screen.findByText("+0.300")).toBeVisible();
  const row = screen.getByRole("button", { name: "Support" }).closest("tr")!;
  fireEvent.click(within(row).getByRole("cell", { name: "10" }));
  await waitFor(() => expect(api.history).toHaveBeenCalledWith("support", "one", 20, undefined));
  const supportPanel = within(screen.getByRole("region", { name: "Support monitoring" }));
  expect(supportPanel.queryByText("+0.300")).not.toBeInTheDocument();
  await act(async () => finish({ ...history, agent: "support", current_n: 1, previous_n: 0, current_mean: -0.2, points: [] }));
  expect(screen.getByText("-0.200")).toBeVisible();
  expect(supportPanel.queryByText("+0.300")).not.toBeInTheDocument();
  fireEvent.click(supportPanel.getByRole("combobox", { name: "Reward model" }));
  fireEvent.click(await screen.findByRole("option", { name: "Model two" }));
  await waitFor(() => expect(api.history).toHaveBeenCalledWith("support", "two", 20, undefined));
  expect(screen.queryByText("-0.200")).not.toBeInTheDocument();
  await act(async () => finish({ ...history, model_id: "two", current_n: 0, previous_n: 0, current_mean: null, points: [] }));
});

it("shows accepted and rejected trials, baseline diffs, outcomes, and prompt usage", async () => {
  const program = { id: "program", name: "Support experiment", agent: "codex", scope: "/project", status: "active", reward_model_id: "one", reward_model_name: "Model one", active_revision_id: "r2", active_version: 2, run_count: 140, accepted_count: 1, error: null };
  api.overview.mockResolvedValue({ ...overview, programs: [program] });
  api.history.mockResolvedValue({ ...history, program_id: "program", active_revision_id: "r2", points: [{ ...history.points[0], revision_id: "r2" }] });
  api.detail.mockResolvedValue({ ...program, runs_per_arm: 20, max_rounds: 10, metric: { name: "Task accepted" }, reward_model: { id: "one", name: "Model one", status: "succeeded" },
    revisions: [{ id: "r1", version: 1, content: "Verify parts", rationale: "Original instructions", created_at: "2026-10-08" }, { id: "r2", version: 2, content: "Verify parts\nCheck the VIN", rationale: "Require VIN confirmation", created_at: "2026-10-09" }, { id: "r3", version: 3, content: "Guess parts", rationale: "Try a faster lookup", created_at: "2026-10-10" }],
    revision_stats: [{ revision_id: "r2", assigned: 60, completed: 55, reward: 0.4 }],
    rounds: [{ id: "trial1", number: 1, baseline_id: "r1", candidate_id: "r2", status: "promoted", report: { reason: "Reward improved and business guardrail passed", arms: { baseline: { reward: { mean: 0.1 }, completed: 20, business: { mean: 0.8 } }, candidate: { reward: { mean: 0.4 }, completed: 20, business: { n: 20, mean: 0.95 } } }, reward_change: { mean: 0.3, low: 0.15, high: 0.45 } } }, { id: "trial2", number: 2, baseline_id: "r2", candidate_id: "r3", status: "rejected", report: { reason: "Reward did not improve", arms: {} } }], events: [],
  });
  render(<MonitoringPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Codex" }));
  expect((await screen.findAllByText("Require VIN confirmation"))[0]).toBeVisible();
  expect(screen.getByText("Reward improved and business guardrail passed")).toBeVisible();
  expect(screen.getByText("Reward did not improve")).toBeVisible();
  expect(screen.getByText("99% interval 0.150 to 0.450")).toBeVisible();
  expect(screen.getByText("60 assigned runs · 55 scored runs · mean reward 0.400")).toBeInTheDocument();
  expect(screen.getByText("Changes from baseline v1")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Reward model" })).toBeDisabled();
  expect(api.history).toHaveBeenCalledWith("codex", "one", 20, "program");
  fireEvent.click(screen.getByRole("combobox", { name: "Rolling window" }));
  fireEvent.click(await screen.findByRole("option", { name: "Last 50 scored runs" }));
  await waitFor(() => expect(api.history).toHaveBeenCalledWith("codex", "one", 50, "program"));
});

it("keeps GEPA selection separate from accepted and delivered agent prompts", async () => {
  api.overview.mockResolvedValue({ ...overview, gepa: [{ id: "gepa", skill_name: "Parts skill", status: "succeeded", task_model: "task-model", reward_model_name: "Model one", seed_score: 0.2, best_score: 0.8, candidate_count: 2, created_at: "2026-10-10" }] });
  api.gepa.mockResolvedValue({ id: "gepa", seed_skill: "old skill", best_skill: "better skill", candidates: [{ skill: "old skill", score: 0.2 }, { skill: "better skill", score: 0.8 }] });
  render(<MonitoringPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Parts skill/ }));
  expect(await screen.findByText("Selected by GEPA")).toBeInTheDocument();
  expect(screen.queryByText("accepted", { exact: true })).not.toBeInTheDocument();
  expect(screen.getByText(/agent delivery and acceptance are not recorded here/)).toBeVisible();
  expect(api.gepa).toHaveBeenCalledWith("gepa");
});

it("expands each agent directly below its row and toggles from both the name and chevron", async () => {
  render(<MonitoringPage />);
  const codex = await screen.findByRole("button", { name: "Codex" });
  expect(codex).toHaveAttribute("aria-expanded", "false");
  expect(api.history).not.toHaveBeenCalled();
  const codexRow = codex.closest("tr")!;
  const supportRow = screen.getByRole("button", { name: "Support" }).closest("tr")!;
  fireEvent.click(codex);
  const panel = await screen.findByRole("region", { name: "Codex monitoring" });
  const panelRow = panel.closest("tr")!;
  expect(codexRow.nextElementSibling).toBe(panelRow);
  expect(panelRow.nextElementSibling).toBe(supportRow);
  expect(panel.closest("td")).toHaveAttribute("colspan", "5");
  expect(screen.queryByText("Performance across recorded runs")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Support details" }));
  expect(await screen.findByRole("region", { name: "Support monitoring" })).toBeVisible();
  expect(screen.getByRole("region", { name: "Codex monitoring" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Codex details" }));
  expect(screen.queryByRole("region", { name: "Codex monitoring" })).not.toBeInTheDocument();
  expect(codexRow.nextElementSibling).toBe(supportRow);
  expect(screen.getByRole("region", { name: "Support monitoring" })).toBeVisible();
});
