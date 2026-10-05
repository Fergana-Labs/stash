import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import { buildRows } from "./trace-rows";

function step(index: number, content: string, role: RmStep["role"] = "user"): RmStep {
  return { id: `s${index}`, index, content, role, tool_name: null, tool_input: null, tool_call_id: null, metadata: null };
}

const ann: StepAnnotations = {
  highlights: () => [], commentCount: () => 0, hasQuotes: () => false, flashing: () => false,
  onComment: vi.fn(), onSelectAnnotation: vi.fn(),
};

it("collapses repeated text while preserving both source steps and a disclosure", () => {
  const rows = buildRows([step(0, "Find a piston kit"), step(1, "Find a piston kit")]);
  const onToggle = vi.fn();
  const { container, rerender } = render(<TraceTimeline rows={rows} ann={ann} isExpanded={() => false} onToggle={onToggle} />);
  expect(screen.getAllByText("Find a piston kit")).toHaveLength(1);
  expect(container.querySelector("#step-s0")).toBeInTheDocument();
  expect(container.querySelector("#step-s1")).toBeInTheDocument();
  const disclosure = screen.getByRole("button", { name: "Repeated user message — show" });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(disclosure);
  expect(onToggle).toHaveBeenCalledWith(rows[1]);
  rerender(<TraceTimeline rows={rows} ann={ann} isExpanded={(row) => row.key === "s1"} onToggle={onToggle} />);
  expect(screen.getAllByText("Find a piston kit")).toHaveLength(2);
});

it("does not collapse messages made adjacent only by filtering", () => {
  const rows = buildRows([step(0, "Try again"), step(2, "Try again")]);
  render(<TraceTimeline rows={rows} ann={ann} isExpanded={() => false} onToggle={vi.fn()} />);
  expect(screen.getAllByText("Try again")).toHaveLength(2);
  expect(screen.queryByText(/Repeated user message/)).not.toBeInTheDocument();
});

it("offers keyboard-accessible tool disclosure and identifies the result step", () => {
  const call = { ...step(0, "", "assistant"), tool_name: "lookup_order", tool_input: {}, tool_call_id: "call1" };
  const result = { ...step(1, "Delivered", "tool"), tool_name: "lookup_order", tool_call_id: "call1" };
  const rows = buildRows([call, result]);
  const onToggle = vi.fn();
  render(<TraceTimeline rows={rows} ann={ann} isExpanded={() => true} onToggle={onToggle} />);
  const disclosure = screen.getByRole("button", { name: "Collapse Lookup order tool call" });
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(disclosure);
  expect(onToggle).toHaveBeenCalledWith(rows[0]);
  expect(screen.getByText("Step 2")).toBeVisible();
});

it("shows learned credit on a collapsed tool call and response, with no badge on its observation", () => {
  const call = { ...step(1, "", "assistant"), tool_name: "lookup", tool_input: {}, tool_call_id: "call1" };
  const result = { ...step(2, "Found", "tool"), tool_name: "lookup", tool_call_id: "call1" };
  const rows = buildRows([step(0, "Find a part"), call, result, step(3, "Here it is", "assistant")]);
  const scoredAnn = { ...ann, actionScore: (s: RmStep) => s.role === "assistant" ? {
    reward_model_id: "model", reward_model_name: "Parts evaluator", step_id: s.id,
    score: s.index === 1 ? -2 : 2, credit: s.index === 1 ? -0.5 : 0.5, created_at: "now",
  } : undefined };
  const { container } = render(<TraceTimeline rows={rows} ann={scoredAnn} isExpanded={() => false} onToggle={vi.fn()} />);
  expect(screen.getByText("Credit -0.50")).toBeVisible();
  expect(screen.getByText("Credit +0.50")).toBeVisible();
  expect(screen.getAllByText(/Credit [+-]/)).toHaveLength(2);
  expect(container.querySelector("#step-s1")?.getAttribute("style")).toContain("box-shadow");
  expect(container.querySelector("#step-s0")?.getAttribute("style")).toBeNull();
});
