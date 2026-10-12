import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { RmScoringRun } from "@/lib/types";
import ScoringProgress from "./ScoringProgress";

const now = new Date("2026-10-12T23:07:00Z");
const run: RmScoringRun = { id: "run", trace_id: "trace", reward_model_id: "model", status: "running", error: null, started_at: "2026-10-12T23:06:00Z" };
const progress: NonNullable<RmScoringRun["progress"]> = { stage: "scoring", completed: 20, total: 100, elapsed_seconds: 10, updated_at: now.toISOString() };
afterEach(() => vi.useRealTimers());

it("shows real item progress and an inference ETA, then removes a stale estimate", () => {
  vi.useFakeTimers(); vi.setSystemTime(now);
  render(<ScoringProgress run={{ ...run, progress }} modelName="Demo" />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");
  expect(screen.getByText("20 / 100")).toBeVisible();
  expect(screen.getByText("About 40s scoring left")).toBeVisible();
  expect(screen.getByText("1m 0s elapsed")).toBeVisible();
  act(() => vi.advanceTimersByTime(16000));
  expect(screen.queryByText(/scoring left/)).not.toBeInTheDocument();
  expect(screen.getByText("20 / 100")).toBeVisible();
});

it("keeps queue, GPU startup, checkpoint load and saving indeterminate", () => {
  vi.useFakeTimers(); vi.setSystemTime(now);
  const { rerender } = render(<ScoringProgress run={null} modelName="Demo" />);
  expect(screen.getByText("Submitting scoring request…")).toBeVisible();
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  rerender(<ScoringProgress run={{ ...run, status: "queued" }} modelName="Demo" />);
  expect(screen.getByText("Queued for scoring with Demo…")).toBeVisible();
  expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  for (const [stage, label] of [["starting", "Starting GPU worker"], ["downloading", "Downloading model checkpoint"], ["loading", "Loading model on GPU"], ["saving", "Saving scores"]] as const) {
    rerender(<ScoringProgress run={{ ...run, progress: { ...progress, stage } }} modelName="Demo" />);
    expect(screen.getByText(label + "…")).toBeVisible();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/scoring left/)).not.toBeInTheDocument();
  }
});

it("does not invent an ETA before batches finish or after inference completes", () => {
  vi.useFakeTimers(); vi.setSystemTime(now);
  const { rerender } = render(<ScoringProgress run={{ ...run, progress: { ...progress, completed: 0 } }} modelName="Demo" />);
  expect(screen.queryByText(/scoring left/)).not.toBeInTheDocument();
  rerender(<ScoringProgress run={{ ...run, progress: { ...progress, completed: 100 } }} modelName="Demo" />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  expect(screen.queryByText(/scoring left/)).not.toBeInTheDocument();
});
