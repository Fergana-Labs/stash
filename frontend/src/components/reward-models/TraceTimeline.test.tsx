import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import { buildRows } from "./trace-rows";

beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => vi.unstubAllGlobals());

function step(index: number, content: string, role: RmStep["role"] = "user"): RmStep {
  return { id: `s${index}`, index, content, role, tool_name: null, tool_input: null, tool_call_id: null, metadata: null };
}

const ann: StepAnnotations = {
  highlights: () => [], commentCount: () => 0, hasQuotes: () => false, flashing: () => false,
  onComment: vi.fn(), onSelectAnnotation: vi.fn(),
};

it("separates the task summary from step rows, including a single task starting with a tool call", () => {
  const call = { ...step(0, "", "assistant"), tool_name: "lookup", tool_input: {}, tool_call_id: "call" };
  const scoredAnn = { ...ann, taskScore: () => ({ task: "t1", score: -1, rubricOnly: -1, answer: 0.28, costs: -1.32, hasAnswer: true }) };
  const { container } = render(<TraceTimeline rows={buildRows([call, step(1, "Done", "assistant")])} ann={scoredAnn} isExpanded={() => false} onToggle={vi.fn()} />);
  const summary = screen.getByRole("region", { name: "Task 1 score summary" });
  expect(within(summary).getByText("Steps 1–2")).toBeVisible();
  expect(summary).toHaveTextContent("Final answer+0.28");
  expect(summary).toHaveTextContent("Total work−1.32");
  expect(summary).toHaveTextContent("Task score−1.00");
  expect(container.querySelector("#step-s0")?.contains(summary)).toBe(false);
  expect(container.querySelector("#step-s1")?.contains(summary)).toBe(false);
  expect(summary.closest('[aria-label="Assistant turn"]')).toBeNull();
});

it("shows a task once with its full range when separate sections split its rows", () => {
  const rows = buildRows([step(0, "Request"), step(1, "Done", "assistant")]);
  const scoredAnn = { ...ann, taskScore: () => ({ task: "t1", score: 0.25, rubricOnly: 0.25, answer: 0.3, costs: -0.05, hasAnswer: true }) };
  render(<>{rows.map((row) => <TraceTimeline key={row.key} rows={[row]} taskRows={rows} ann={scoredAnn} isExpanded={() => false} onToggle={vi.fn()} />)}</>);
  expect(screen.getAllByRole("region", { name: "Task 1 score summary" })).toHaveLength(1);
  expect(screen.getByRole("region", { name: "Task 1 score summary" })).toHaveTextContent("Steps 1–2");
});

it("keeps separate task summaries and shows missing answers without inventing a zero score", () => {
  const source = [step(0, "First request"), step(1, "Second request")];
  const scoredAnn = { ...ann, taskScore: (s: RmStep) => ({ task: `t${s.index + 1}`, score: -0.05, rubricOnly: -0.05, answer: null, costs: -0.05, hasAnswer: false }) };
  render(<TraceTimeline rows={buildRows(source)} ann={scoredAnn} isExpanded={() => false} onToggle={vi.fn()} />);
  for (const n of [1, 2]) {
    const summary = screen.getByRole("region", { name: `Task ${n} score summary` });
    expect(summary).toHaveTextContent(`Step ${n}`);
    expect(summary).toHaveTextContent("Final answerNo answer");
    expect(summary).not.toHaveTextContent("Limited to");
  }
});

it("gives every recorded role a number in the left gutter without a separate reader", () => {
  const source = [step(0, "Initial message", "system"), step(1, "A request"), step(2, "<turn_aborted>Interrupted</turn_aborted>", "system")];
  render(<TraceTimeline rows={buildRows(source)} ann={ann} isExpanded={() => true} onToggle={vi.fn()} />);
  expect(screen.getByLabelText("Step 3")).toHaveTextContent(/^3$/);
  expect(screen.getByLabelText("Step 1")).toHaveClass("left-0");
  expect(screen.getByText("<turn_aborted>Interrupted</turn_aborted>")).toBeVisible();
  expect(screen.queryByRole("button", { name: /^Read (system|user) message$/ })).not.toBeInTheDocument();
  expect(screen.queryByText("System instructions")).not.toBeInTheDocument();
});

it("starts a long message expanded and supports collapsing and reopening it", () => {
  const height = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(1000);
  try {
    const { container } = render(<TraceTimeline rows={buildRows([step(0, "Long text", "assistant")])} ann={ann} isExpanded={() => true} onToggle={vi.fn()} />);
    const body = container.querySelector('[data-step-content]')!.parentElement!;
    expect((body as HTMLElement).style.maxHeight).toBe("");
    expect(screen.queryByRole("button", { name: "Read full message" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse to preview" })).not.toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Collapse to preview" }));
    expect(body).toHaveStyle({ maxHeight: "160px" });
    fireEvent.click(screen.getByRole("button", { name: "Read full message" }));
    expect((body as HTMLElement).style.maxHeight).toBe("");
    fireEvent.keyDown(screen.getByRole("button", { name: "Collapse to preview" }), { key: "Escape" });
    expect(body).toHaveStyle({ maxHeight: "160px" });
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  } finally { height.mockRestore(); }
});

it("keeps the collapse control above long content and restores the message in view", () => {
  const height = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(4000);
  let nextFrame: FrameRequestCallback | undefined;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { nextFrame = callback; return 1; });
  try {
    const { container } = render(<div data-trace-scroll><TraceTimeline rows={buildRows([step(0, "Long text", "system")])} ann={ann} isExpanded={() => true} onToggle={vi.fn()} /></div>);
    const scroller = container.firstElementChild as HTMLElement;
    scroller.scrollTop = 2000;
    scroller.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
    scroller.scrollTo = vi.fn();
    const close = screen.getByRole("button", { name: "Collapse to preview" });
    expect(close.parentElement).toHaveClass("sticky", "top-8");
    const frame = close.parentElement!.parentElement!;
    frame.getBoundingClientRect = () => ({ top: -1500 }) as DOMRect;
    fireEvent.click(close);
    act(() => nextFrame?.(0));
    expect(scroller.scrollTo).toHaveBeenCalledWith({ top: 360, behavior: "instant" });
    expect(screen.getByRole("button", { name: "Read full message" })).toHaveFocus();
  } finally { height.mockRestore(); }
});

it("collapses repeated text while preserving both source steps and a disclosure", () => {
  const rows = buildRows([step(0, "Find a piston kit"), step(1, "Find a piston kit")]);
  const onToggle = vi.fn();
  const { container, rerender } = render(<TraceTimeline rows={rows} ann={ann} isExpanded={(row) => row.key === "s0"} onToggle={onToggle} />);
  expect(screen.getAllByText("Find a piston kit")).toHaveLength(1);
  expect(container.querySelector("#step-s0")).toBeInTheDocument();
  expect(container.querySelector("#step-s1")).toBeInTheDocument();
  const disclosure = screen.getByRole("button", { name: "Expand repeated user message" });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(disclosure);
  expect(onToggle).toHaveBeenCalledWith(rows[1]);
  rerender(<TraceTimeline rows={rows} ann={ann} isExpanded={() => true} onToggle={onToggle} />);
  expect(screen.getAllByText("Find a piston kit")).toHaveLength(2);
});

it("does not collapse messages made adjacent only by filtering", () => {
  const rows = buildRows([step(0, "Try again"), step(2, "Try again")]);
  render(<TraceTimeline rows={rows} ann={ann} isExpanded={() => true} onToggle={vi.fn()} />);
  expect(screen.getAllByText("Try again")).toHaveLength(2);
  expect(screen.queryByText(/Repeated user message/)).not.toBeInTheDocument();
});

it.each(["call1", null])("offers keyboard-accessible tool disclosure and groups output, with call ID %s", (callId) => {
  const call = { ...step(0, "", "assistant"), tool_name: "lookup_order", tool_input: {}, tool_call_id: callId };
  const result = { ...step(1, "Delivered", "tool"), tool_name: "lookup_order", tool_call_id: callId };
  const rows = buildRows([call, result]);
  const onToggle = vi.fn();
  render(<TraceTimeline rows={rows} ann={ann} isExpanded={() => true} onToggle={onToggle} />);
  const disclosure = screen.getByRole("button", { name: "Collapse Lookup order tool call" });
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(disclosure);
  expect(onToggle).toHaveBeenCalledWith(rows[0]);
  expect(screen.queryByText("Step 2")).not.toBeInTheDocument();
  expect(screen.getByText("Output")).toBeVisible();
  expect(screen.queryByText("Details")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand tool output" }));
  expect(screen.getByText("Delivered")).toBeVisible();
});

it("labels a separate tool result as output even when collapsed", () => {
  const result = { ...step(0, "Part found", "tool"), tool_name: "find_parts_for_vehicle" };
  render(<TraceTimeline rows={buildRows([result])} ann={ann} isExpanded={() => false} onToggle={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Expand Find parts for vehicle tool result" })).toHaveTextContent("Output · Find parts for vehicle");
});

it("shows the recorded action and exposes tool help and exact inputs on focus", async () => {
  const input = { title: "Inspect Slack notifications", code: "await tab.getAXState();" };
  const call = { ...step(0, "", "assistant"), tool_name: "js", tool_input: input, tool_call_id: "call1" };
  const { rerender } = render(<TraceTimeline rows={buildRows([call])} ann={ann} isExpanded={() => false} onToggle={vi.fn()} />);
  const disclosure = screen.getByRole("button", { name: "Expand Js tool call" });
  expect(disclosure).toHaveTextContent(input.title);
  expect(screen.queryByText(input.code)).not.toBeInTheDocument();
  fireEvent.focus(screen.getByLabelText("About Js"));
  expect(await screen.findByRole("tooltip")).toHaveTextContent("JavaScript execution tool");
  fireEvent.blur(screen.getByLabelText("About Js"));
  fireEvent.focus(disclosure);
  expect(await screen.findByRole("tooltip")).toHaveTextContent(JSON.stringify(input, null, 2).replace(/\s+/g, " "));
  fireEvent.blur(disclosure);
  rerender(<TraceTimeline rows={buildRows([call])} ann={ann} isExpanded={() => true} onToggle={vi.fn()} />);
  expect(within(screen.getByLabelText("Tool inputs")).getByText("Inputs")).toBeVisible();
  const tool = screen.getByRole("group", { name: "Tool" });
  expect(within(tool).getByLabelText("About Js")).toBeVisible();
  expect(tool.compareDocumentPosition(screen.getByLabelText("Tool inputs")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole("button", { name: "Expand input code" })).toBeVisible();
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
  expect(screen.getByLabelText("Action credit -0.50")).toBeVisible();
  expect(screen.getByLabelText("Action credit +0.50")).toBeVisible();
  expect(screen.getAllByLabelText(/Action credit [+-]/)).toHaveLength(2);
  expect(container.querySelector("#step-s1")?.getAttribute("style")).toBeNull();
  expect(container.querySelector("#step-s0")?.getAttribute("style")).toBeNull();
});


it("offers new message comments alongside existing comment navigation", () => {
  const message = step(0, "Context", "system");
  const onComment = vi.fn();
  const onViewComments = vi.fn();
  render(<TraceTimeline rows={buildRows([message])} ann={{ ...ann, commentCount: () => 2, onComment, onViewComments }} isExpanded={() => true} onToggle={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Comment on message" }));
  expect(onComment).toHaveBeenCalledWith(message);
  fireEvent.click(screen.getByRole("button", { name: "View 2 comments on this message" }));
  expect(onViewComments).toHaveBeenCalledWith(message);
});

it("keeps the score visible without exposing the grading breakdown", () => {
  const message = step(0, "Finished", "assistant");
  render(<TraceTimeline rows={buildRows([message])} ann={{ ...ann, reward: () => ({ base: -0.03, baseParts: [{ text: "Standard cost of a lookup", value: -0.03 }], grade: null, score: -0.03, shared: [], sharedTotal: 0, total: -0.03, isAnswer: false }) }} isExpanded={() => true} onToggle={vi.fn()} />);
  expect(screen.getByTitle("Step score")).toHaveTextContent("−0.03");
  expect(screen.queryByText("Standard cost of a lookup")).not.toBeInTheDocument();
  expect(screen.queryByText("Score for this step")).not.toBeInTheDocument();
});
