import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmTraceDetail } from "@/lib/types";
import ModelTraceConversation from "./ModelTraceConversation";

beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => vi.unstubAllGlobals());
const trace = { id: "trace", title: "Task", steps: [
  { id: "system", index: 0, role: "system", content: "Private setup instructions", tool_name: null, tool_input: null, metadata: null },
  { id: "user", index: 1, role: "user", content: "Find **the part**", tool_name: null, tool_input: null, metadata: null },
  { id: "call", index: 2, role: "assistant", content: "", tool_name: "lookup", tool_call_id: "lookup1", tool_input: { query: "crosshead" }, metadata: null },
  { id: "result", index: 3, role: "tool", content: "{\"part\":\"123\"}", tool_name: "lookup", tool_call_id: "lookup1", tool_input: null, metadata: null },
] } as unknown as RmTraceDetail;

it("renders Markdown and collapses context and paired tool details like the main viewer", () => {
  const { container } = render(<ModelTraceConversation trace={trace} scores={[]} modelName="Parts accuracy" />);
  fireEvent.click(screen.getByRole("button", { name: "Expand user message" }));
  expect(container.querySelector("strong")).toHaveTextContent("the part");
  expect(container.querySelector('[data-step-id="system"] [data-step-content]')).toBeNull();
  expect(screen.queryByRole("button", { name: "Comment on message" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Context"));
  fireEvent.click(screen.getByRole("button", { name: "Expand system message" }));
  expect(screen.getByText("Private setup instructions")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Expand Lookup tool call" }));
  expect(screen.getByRole("group", { name: "Tool" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Expand tool output" }));
  expect(screen.getByRole("button", { name: "Copy tool output" })).toBeVisible();
});

it("keeps learned model credits attached to the tool call after pairing its result", () => {
  render(<ModelTraceConversation trace={trace} scores={[{ step_id: "call", credit: -0.4, score: -2 } as never]} modelName="Parts accuracy" />);
  const grade = screen.getByLabelText("Action credit -0.40");
  expect(grade).toHaveAttribute("title", expect.stringContaining("Parts accuracy"));
  expect(grade.closest("[data-step-id]")).toHaveAttribute("data-step-id", "call");
});

it("keeps scroll anchors unique when the same trace is open under multiple models", () => {
  const { container } = render(<><ModelTraceConversation trace={trace} scores={[]} modelName="One" /><ModelTraceConversation trace={trace} scores={[]} modelName="Two" /></>);
  const ids = [...container.querySelectorAll("[data-step-id]")].map((row) => row.id);
  expect(new Set(ids).size).toBe(ids.length);
});
