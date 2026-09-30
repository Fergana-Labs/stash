import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmStep } from "@/lib/types";
import TraceMinimap from "./TraceMinimap";

const steps: RmStep[] = [0, 1, 2].map((index) => ({
  id: String(index), index, role: "assistant", content: "Response",
  tool_name: null, tool_input: null, tool_call_id: null, metadata: null,
}));

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    disconnect() {}
  });
});
afterEach(() => vi.unstubAllGlobals());

function renderMap(visibleSteps = steps, onJump = vi.fn()) {
  const container = document.createElement("div");
  const content = document.createElement("div");
  container.append(content);
  Object.defineProperties(container, {
    scrollHeight: { value: 1000 },
    clientHeight: { value: 500 },
  });
  const header = document.createElement("div");
  header.getBoundingClientRect = () => ({ bottom: 100 }) as DOMRect;
  for (const step of visibleSteps) {
    const element = document.createElement("div");
    element.id = `step-${step.id}`;
    // Several short rows fit below the graph even at the bottom.
    const rect = { bottom: 200 + step.index * 50 } as DOMRect;
    element.getBoundingClientRect = () => rect;
    element.getClientRects = () => [rect] as unknown as DOMRectList;
    content.append(element);
  }
  render(<TraceMinimap steps={steps} annotations={[]} scroller={{ current: container }} navigation={{ current: header }} onJump={onJump} />);
  return container;
}

it("reaches the final step at the bottom even when earlier steps are still visible", async () => {
  const container = renderMap();
  container.scrollTop = 500;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 3: Assistant" })).toHaveAttribute("aria-current", "step"));
  container.scrollTop = 400;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 1: Assistant" })).toHaveAttribute("aria-current", "step"));
});

it("uses the final displayed step when filters hide the end of the trace", async () => {
  const container = renderMap(steps.slice(0, 2));
  container.scrollTop = 500;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 2: Assistant" })).toHaveAttribute("aria-current", "step"));
});

it("scrubs across steps, clamps at the ends, and stops on release", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump);
  const map = screen.getByRole("group", { name: "Step map" });
  map.getBoundingClientRect = () => ({ left: 100, width: 300 }) as DOMRect;
  const capture = vi.spyOn(map, "setPointerCapture");
  fireEvent.pointerDown(map, { pointerId: 1, button: 0, clientX: 110 });
  expect(capture).toHaveBeenCalledWith(1);
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 250 });
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 260 });
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 500 });
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 50 });
  fireEvent.pointerUp(map, { pointerId: 1 });
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 350 });
  expect(onJump.mock.calls).toEqual([[0], [1], [2], [0]]);
});

it("ends scrubbing when the pointer is cancelled and retains keyboard activation", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump);
  const map = screen.getByRole("group", { name: "Step map" });
  map.getBoundingClientRect = () => ({ left: 0, width: 300 }) as DOMRect;
  fireEvent.pointerDown(map, { pointerId: 1, button: 0, clientX: 10 });
  fireEvent.pointerCancel(map, { pointerId: 1 });
  fireEvent.pointerMove(map, { pointerId: 1, clientX: 250 });
  fireEvent.click(screen.getByRole("button", { name: "Step 3: Assistant" }), { detail: 0 });
  expect(onJump.mock.calls).toEqual([[0], [2]]);
});
