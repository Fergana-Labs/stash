import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import TraceTrainingStatus from "./TraceTrainingStatus";

it("links to the created model and follows its training lifecycle", () => {
  const model = { id: "m1", name: "Trace evaluator", status: "queued" as const, error: null, created_at: "2026-10-08", finished_at: null };
  const { rerender } = render(<TraceTrainingStatus models={[model]} />);
  expect(screen.getByRole("link", { name: "Trace evaluator: Model created" })).toHaveAttribute("href", "/reward-models/models#model-m1");
  rerender(<TraceTrainingStatus models={[{ ...model, status: "running" }]} />);
  expect(screen.getByRole("link")).toHaveAccessibleName("Trace evaluator: Training model…");
  rerender(<TraceTrainingStatus models={[{ ...model, status: "succeeded" }]} />);
  expect(screen.getByRole("link")).toHaveAccessibleName("Trace evaluator: Model ready");
  rerender(<TraceTrainingStatus models={[{ ...model, status: "failed", error: "Worker stopped" }]} />);
  expect(screen.getByRole("link")).toHaveAttribute("title", "Trace evaluator: Training needs attention — Worker stopped");
  rerender(<TraceTrainingStatus models={[]} />);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
