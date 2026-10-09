import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import type { RmRewardModel } from "@/lib/types";
import ModelTiming, { trainingStage } from "./ModelTiming";

const model = { status: "queued", created_at: new Date().toISOString(), compute: "modal" } as RmRewardModel;
const estimate = { basis: "history", scope: "job", sample_count: 3, lower_seconds: 120, upper_seconds: 240, overdue: false, excludes_queue: true } as const;

it("makes queue waits and unknown timing explicit", () => {
  const { rerender } = render(<ModelTiming model={model} />);
  expect(screen.getByText("Estimating…")).toHaveAttribute("title", expect.stringContaining("Waiting for a worker"));
  rerender(<ModelTiming model={{ ...model, estimated_timing: estimate }} />);
  expect(screen.getByText("≈2–4m + queue")).toHaveAttribute("title", expect.stringContaining("3 comparable completed runs"));
});

it("updates to live training timing, late estimates, and completed states", () => {
  const running = { ...model, status: "running" as const, estimated_timing: { ...estimate, basis: "batches" as const, scope: "training" as const, excludes_queue: false } };
  const { rerender } = render(<ModelTiming model={running} />);
  expect(screen.getByText("≈2–4m training")).toHaveAttribute("title", expect.stringContaining("evaluation, scoring and upload follow"));
  rerender(<ModelTiming model={{ ...running, estimated_timing: { ...running.estimated_timing, overdue: true } }} />);
  expect(screen.getByText("Taking longer…")).toBeVisible();
  rerender(<ModelTiming model={{ ...running, status: "succeeded" }} />);
  expect(screen.getByText("—")).toBeVisible();
  rerender(<ModelTiming model={{ ...running, status: "failed" }} />);
  expect(screen.getByText("—")).toBeVisible();
});

it("uses actual stages and does not let stale progress override failure", () => {
  const loading = { ...model, status: "running" as const, progress: { stage: "loading" as const, completed: 0, total: 0, elapsed_seconds: 0, updated_at: new Date().toISOString() } };
  expect(trainingStage(loading)).toBe("Loading model");
  expect(trainingStage({ ...loading, status: "failed" })).toBe("Failed");
});
