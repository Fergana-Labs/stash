import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { wbLabelAssessment, type ReviewSample } from "@/lib/workbench-api";
import { SampleCard } from "./ReviewSamples";

vi.mock("@/lib/workbench-api", async (original) => ({ ...await original<typeof import("@/lib/workbench-api")>(), wbLabelAssessment: vi.fn() }));

it("requires a human-selected label and saves it without requesting any changes", async () => {
  vi.mocked(wbLabelAssessment).mockResolvedValue({ review_status: "accepted", change_kind: "label_only" } as never);
  const onLabeled = vi.fn().mockResolvedValue(undefined);
  const sample = { reason: "sample", assessment: { id: "assessment", trace_id: "trace", target_step_id: "claim", criterion_name: "Test reporting", verdict: "meets", status: "completed", input_snapshot: { context_events: [{ role: "tool", content: "FAILED" }, { role: "assistant", content: "All tests pass" }] } } } as ReviewSample;
  render(<SampleCard sample={sample} onLabeled={onLabeled} />);
  fireEvent.click(screen.getByText("Test reporting · Representative sample"));
  expect(screen.getByRole("button", { name: "Save reviewed label" })).toBeDisabled();
  expect(screen.getByRole("link", { name: "Inspect claim and context in trace" })).toHaveAttribute("href", "/reward-models/traces/trace?assessment=assessment#step-claim");
  fireEvent.change(screen.getByRole("combobox", { name: "Your reviewed verdict" }), { target: { value: "violates" } });
  fireEvent.click(screen.getByRole("button", { name: "Save reviewed label" }));
  await waitFor(() => expect(wbLabelAssessment).toHaveBeenCalledWith("assessment", "violates", undefined));
  expect(onLabeled).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/does not draft or release a change/)).toBeVisible();
});
