import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WizardProvider } from "@/components/wizard/wizard-ui";
import ResultsPanel from "./ResultsPanel";

const api = vi.hoisted(() => ({ imGet: vi.fn(), imExamples: vi.fn() }));
const wizard = vi.hoisted(() => ({ wzReport: vi.fn(), wzTrain: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);
vi.mock("@/lib/wizard-api", () => wizard);
vi.mock("@/components/wizard/cards/AgreementCard", () => ({ default: () => null }));

const report = {
  version: 1, is_live: true, counts: { train: 1, held_out: 1, labels: { send: 1, rewrite: 1 } },
  holdout: { n: 1, accuracy: 1, ece: 0, reliability: [], rows: [{ example_id: "e", label: "send", predicted: "send" }],
    by_difficulty: [{ bucket: 1, n: 1, accuracy: 1, difficulty: [10, 20] }, { bucket: 2, n: 1, accuracy: 0, difficulty: [20, 40] }] },
  leaderboard: [{ name: "Jev zero-shot", accuracy: 1 }], learning_curve: [], drivers: [], warnings: [],
  gate: { passed: true, active_version: null, checks: [], pinned: null },
};

beforeEach(() => {
  vi.clearAllMocks();
  api.imExamples.mockResolvedValue([]);
  wizard.wzReport.mockResolvedValue({ report });
  api.imGet.mockResolvedValue({
    model: { id: "m", output_type: "choice" }, counts: { labeled: 2 },
    active: { provider: "agent_judge", labels: [{ id: "send" }, { id: "rewrite" }] },
    draft: { provider: "jev", labels: [{ id: "send" }, { id: "rewrite" }], head_stale: true },
  });
});

function renderResults() {
  return render(<WizardProvider value={{ modelId: "m", send: vi.fn(), refresh: vi.fn(), version: 0, busy: false }}><ResultsPanel /></WizardProvider>);
}

it("retains classification and difficulty metrics and names the judge used by the live report", async () => {
  renderResults();
  expect(await screen.findByText(/Agent Judge alone, without your labels/)).toBeVisible();
  fireEvent.click(screen.getByText("How the score is built"));
  expect(screen.getByRole("table", { name: "Per-class metrics" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "Recall" })).toBeVisible();
  expect(screen.getByRole("img", { name: "Held-out accuracy by difficulty" })).toBeVisible();
});

it("shows per-issue results for multi-label evals without treating label sets as separate classes", async () => {
  api.imGet.mockResolvedValue({ model: { id: "m", output_type: "multi" }, counts: { labeled: 2 }, draft: null,
    active: { provider: "jev", labels: [{ id: "unreadable" }, { id: "unsupported" }] } });
  wizard.wzReport.mockResolvedValue({ report: { ...report, holdout: { ...report.holdout, accuracy: 0,
    rows: [{ example_id: "e", label: "unreadable+unsupported", predicted: "unreadable" }] } } });
  renderResults();
  expect(await screen.findByText("Per issue")).toBeVisible();
  fireEvent.click(screen.getByText("How the score is built"));
  expect(screen.queryByRole("table", { name: "Per-class metrics" })).not.toBeInTheDocument();
});
