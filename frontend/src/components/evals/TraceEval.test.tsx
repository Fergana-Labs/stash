import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import TraceEval from "./TraceEval";
import type { RmTraceDetail } from "@/lib/types";

const api = vi.hoisted(() => ({ imList: vi.fn(), imGet: vi.fn(), imPredict: vi.fn() }));
vi.mock("@/lib/intuition-api", () => api);

it("evaluates a trace without including existing scores or annotations in the input", async () => {
  api.imList.mockResolvedValue({ models: [{ id: "ready", name: "Safety", active_version_id: "v1" }, { id: "draft", name: "Uncalibrated", active_version_id: null }] });
  api.imGet.mockResolvedValue({ active: { rubric: [] } });
  api.imPredict.mockResolvedValue({ label: "good", confidence: 0.9, probabilities: { good: 0.9, bad: 0.1 }, rubric: {}, version: 1 });
  const trace = { id: "trace", title: "A task", steps: [{ index: 0, role: "assistant", content: "Original answer", tool_name: null, tool_input: null }], annotations: [{ comment: "Expected good" }], scores: [{ score: 1 }] } as unknown as RmTraceDetail;
  render(<TraceEval trace={trace} />);
  fireEvent.click(screen.getByRole("button", { name: "Run eval" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(await screen.findByRole("region", { name: "Trace eval scorecard" })).toBeVisible();
  expect(api.imPredict).toHaveBeenCalledWith("ready", { title: "A task", trace_id: "trace", steps: [{ index: 0, role: "assistant", content: "Original answer", tool_name: null, tool_input: null }] });
  expect(screen.getByRole("link", { name: "Review this call or correct the eval" })).toHaveAttribute("href", "/reward-models/evals/ready");
  expect(screen.queryByText("Uncalibrated")).not.toBeInTheDocument();
});
