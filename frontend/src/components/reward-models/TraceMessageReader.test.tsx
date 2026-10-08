import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import TraceMessageReader from "./TraceMessageReader";

function step(index: number, role: RmStep["role"], content: string): RmStep {
  return { id: `s${index}`, index, role, content, tool_name: null, tool_input: null, tool_call_id: null, metadata: null };
}
const steps = [
  step(0, "system", "<skills_instructions>\n# Rules\nUse **care** and [literal] text.\n</skills_instructions>"),
  step(1, "user", "Buy a burrito"),
  step(2, "assistant", "Ordered"),
  step(3, "system", "<turn_aborted>Interrupted [literal]</turn_aborted>"),
];
const props = { steps, stepId: "s0", numberOf: (s: RmStep) => s.index + 1, onClose: vi.fn(), onReveal: vi.fn() };

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollTo = vi.fn();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
});
afterEach(() => vi.restoreAllMocks());

it("reads any recorded role, filters system events in place, and jumps back to the correct source", () => {
  render(<TraceMessageReader {...props} />);
  expect(screen.getByRole("heading", { name: "Rules" })).toBeVisible();
  fireEvent.change(screen.getByLabelText("Message role"), { target: { value: "system" } });
  expect(screen.getByRole("status")).toHaveTextContent("1 of 2 messages");
  fireEvent.click(screen.getByRole("button", { name: "Next message" }));
  expect(screen.getByRole("status")).toHaveTextContent("2 of 2 messages");
  expect(screen.getByText("Step 4", { exact: true })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Show in trace" }));
  expect(props.onReveal).toHaveBeenCalledWith("s3");
  expect(screen.queryByText("System instructions")).not.toBeInTheDocument();
});

it("searches literal raw text across messages, including envelopes, with source-preserving highlights", () => {
  render(<TraceMessageReader {...props} />);
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "[literal]" } });
  expect(screen.getByRole("status")).toHaveTextContent("1 of 2 messages");
  expect(screen.getByRole("button", { name: "Raw" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Message content").textContent).toBe(steps[0].content);
  expect(screen.getByLabelText("Message content").querySelector("mark")).toHaveTextContent("[literal]");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "turn_aborted" } });
  expect(screen.getByRole("status")).toHaveTextContent("1 of 1 messages");
  expect(screen.getByLabelText("Message content").textContent).toBe(steps[3].content);
  expect(screen.getByRole("button", { name: "Match 1 of 2" })).toBeVisible();
  fireEvent.keyDown(screen.getByRole("searchbox"), { key: "Enter" });
  expect(screen.getByRole("button", { name: "Match 2 of 2" })).toBeVisible();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "absent" } });
  expect(screen.getByText("No messages match your search.")).toBeVisible();
});

it("copies unmodified message text and tool input and restores focus on close", async () => {
  const opener = document.createElement("button");
  document.body.append(opener);
  opener.focus();
  const { unmount } = render(<TraceMessageReader {...props} />);
  expect(screen.getByRole("complementary", { name: "Message reader" })).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "Copy raw message" }));
  await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(steps[0].content));
  fireEvent.keyDown(screen.getByRole("complementary"), { key: "Escape" });
  expect(props.onClose).toHaveBeenCalled();
  unmount();
  expect(opener).toHaveFocus();
  opener.remove();
  const call = { ...step(4, "assistant", "Calling search"), tool_name: "search", tool_input: { query: "burrito" } };
  render(<TraceMessageReader {...props} steps={[call]} stepId={call.id} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy raw message" }));
  await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenLastCalledWith('Calling search\n\n{\n  "query": "burrito"\n}'));
});
