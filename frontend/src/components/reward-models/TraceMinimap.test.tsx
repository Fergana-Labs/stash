import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RmActionScore, RmStep } from "@/lib/types";
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

function renderMap(visibleSteps = steps, onJump = vi.fn(), actionScores = new Map([["0", { step_id: "0", credit: 0.25 } as RmActionScore]])) {
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
    const rect = { top: 150 + step.index * 50, bottom: 200 + step.index * 50 } as DOMRect;
    element.getBoundingClientRect = () => rect;
    element.getClientRects = () => [rect] as unknown as DOMRectList;
    content.append(element);
  }
  render(<TraceMinimap steps={steps} annotations={[]} actionScores={actionScores} scroller={{ current: container }} navigation={{ current: header }} onJump={onJump} />);
  return container;
}

it("reaches the final step at the bottom even when earlier steps are still visible", async () => {
  const container = renderMap();
  container.scrollTop = 500;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 3: Response, awaiting score" })).toHaveAttribute("aria-current", "step"));
  container.scrollTop = 400;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 1: Response, credit +0.25" })).toHaveAttribute("aria-current", "step"));
});

it("shows credit through height and keeps action type colors and retains keyboard step navigation", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump, new Map([["0", { step_id: "0", credit: -0.4 } as RmActionScore]]));
  const scored = screen.getByRole("button", { name: "Step 1: Response, credit -0.40" });
  expect(scored.lastElementChild).toHaveStyle({ height: "20%", top: "50%" });
  expect(scored.lastElementChild).toHaveClass("bg-blue-500");
  const unscored = screen.getByRole("button", { name: "Step 2: Response, awaiting score" });
  expect(unscored.lastElementChild).toHaveStyle({ height: "0%" });
  expect(unscored.lastElementChild).toHaveClass("bg-blue-500");
  expect(screen.queryByLabelText("Action credit legend")).not.toBeInTheDocument();
  expect(screen.queryByText(/Only assistant responses and tool calls are graded/)).not.toBeInTheDocument();
  expect(screen.queryByText("User", { exact: true })).not.toBeInTheDocument();
  expect(screen.getByText("Step 1 of 3", { exact: true })).toBeVisible();
  fireEvent.keyDown(scored, { key: "ArrowRight" });
  expect(onJump).toHaveBeenCalledWith(1);
});

it("uses the final displayed step when filters hide the end of the trace", async () => {
  const container = renderMap(steps.slice(0, 2));
  container.scrollTop = 500;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Step 2: Response, awaiting score" })).toHaveAttribute("aria-current", "step"));
});

it("plots equal positive and negative credits equally around zero, keeping zero distinct from ungraded", () => {
  renderMap(steps, vi.fn(), new Map([
    ["0", { step_id: "0", credit: 0.4 } as RmActionScore],
    ["1", { step_id: "1", credit: -0.4 } as RmActionScore],
    ["2", { step_id: "2", credit: 0 } as RmActionScore],
  ]));
  const positive = screen.getByRole("button", { name: "Step 1: Response, credit +0.40" });
  const negative = screen.getByRole("button", { name: "Step 2: Response, credit -0.40" });
  const zero = screen.getByRole("button", { name: "Step 3: Response, credit 0.00" });
  expect(positive.querySelector("[data-credit-bar]")).toHaveStyle({ height: "20%", bottom: "50%" });
  expect(negative.querySelector("[data-credit-bar]")).toHaveStyle({ height: "20%", top: "50%" });
  expect(zero.querySelector("[data-credit-bar]")).toHaveStyle({ height: "0%" });
  expect(zero.querySelector("[data-zero-marker]")).toBeInTheDocument();
  expect(zero).not.toHaveAccessibleName(/awaiting score/);
  expect(screen.getByLabelText("Step credit scale: −1 to +1, with zero in the middle")).toBeVisible();
});

it("defaults to fixed limits and can fit the largest absolute credit without changing the selected step", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump, new Map([
    ["0", { step_id: "0", credit: 0.1 } as RmActionScore],
    ["1", { step_id: "1", credit: -0.4 } as RmActionScore],
  ]));
  const positive = screen.getByRole("button", { name: "Step 1: Response, credit +0.10" });
  const negative = screen.getByRole("button", { name: "Step 2: Response, credit -0.40" });
  expect(screen.getByRole("button", { name: "±1" })).toHaveAttribute("aria-pressed", "true");
  expect(positive.lastElementChild).toHaveStyle({ height: "5%" });
  expect(negative.lastElementChild).toHaveStyle({ height: "20%" });
  fireEvent.click(screen.getByRole("button", { name: "Fit" }));
  expect(positive.lastElementChild).toHaveStyle({ height: "12.5%" });
  expect(negative.lastElementChild).toHaveStyle({ height: "50%" });
  fireEvent.click(negative);
  fireEvent.click(screen.getByRole("button", { name: "±1" }));
  expect(screen.getByRole("button", { name: "±1" })).toHaveAttribute("aria-pressed", "true");
  expect(positive.lastElementChild).toHaveStyle({ height: "5%" });
  expect(negative.lastElementChild).toHaveStyle({ height: "20%" });
  expect(negative).toHaveAttribute("aria-current", "step");
  expect(onJump).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Fit" }));
  expect(negative.lastElementChild).toHaveStyle({ height: "50%" });
});

it("keeps zero and unscored steps flat when there is no nonzero credit to fit", () => {
  renderMap(steps, vi.fn(), new Map([["0", { step_id: "0", credit: 0 } as RmActionScore]]));
  expect(screen.getByLabelText("Step credit scale: −1 to +1, with zero in the middle")).toBeVisible();
  for (const button of screen.getByRole("group", { name: "Step map" }).querySelectorAll("button")) {
    expect(button.querySelector("[data-credit-bar]")).toHaveStyle({ height: "0%" });
    expect(button.querySelector("[data-zero-marker]")).toHaveClass("h-px");
  }
  expect(screen.getByRole("button", { name: "Step 2: Response, awaiting score" })).toBeVisible();
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
  fireEvent.click(screen.getByRole("button", { name: "Step 3: Response, awaiting score" }), { detail: 0 });
  expect(onJump.mock.calls).toEqual([[0], [2]]);
});

it("jumps to the clicked bar even when its position falls outside an equal-width bucket", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump);
  const map = screen.getByRole("group", { name: "Step map" });
  map.getBoundingClientRect = () => ({ left: 100, width: 300 }) as DOMRect;
  fireEvent.pointerDown(screen.getByRole("button", { name: "Step 3: Response, awaiting score" }).lastElementChild!, { pointerId: 1, button: 0, clientX: 290 });
  expect(onJump).toHaveBeenCalledWith(2);
});

it("keeps a clicked user dot active after scrolling below the sticky breadcrumb", async () => {
  const mixed = [steps[0], { ...steps[1], role: "user" }, steps[2]] as RmStep[];
  const container = document.createElement("div");
  container.innerHTML = '<div><div id="step-0"></div><div id="step-1"></div><div id="step-2"></div></div>';
  container.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
  const header = document.createElement("div");
  header.getBoundingClientRect = () => ({ bottom: 100 }) as DOMRect;
  let tops = [140, 440, 740];
  for (const [index, element] of [...container.querySelectorAll<HTMLElement>("[id]")].entries()) {
    element.getBoundingClientRect = () => ({ top: tops[index] }) as DOMRect;
    element.getClientRects = () => [element.getBoundingClientRect()] as unknown as DOMRectList;
  }
  const onJump = vi.fn(() => {
    // Landing below the 32px breadcrumb + 8px gap leaves the previous row above it.
    tops = [-160, 140, 440];
    fireEvent.scroll(container);
  });
  render(<TraceMinimap steps={mixed} annotations={[]} actionScores={new Map([["0", { credit: 0 } as RmActionScore]])} scroller={{ current: container }} navigation={{ current: header }} onJump={onJump} />);
  const user = screen.getByRole("button", { name: "Step 2: User" });
  fireEvent.pointerDown(user.querySelector("[data-zero-marker]")!, { pointerId: 1, button: 0 });
  fireEvent.pointerUp(user, { pointerId: 1 });
  expect(onJump).toHaveBeenCalledWith(1);
  // Wait for the scroll observer, which previously overwrote the clicked index.
  await act(async () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(user).toHaveAttribute("aria-current", "step");
  expect(screen.getByText("Step 2 of 3")).toBeVisible();
  tops = [-460, -160, 140];
  fireEvent.wheel(container);
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByText("Step 3 of 3")).toBeVisible());
});

it.each([480, 500])("preserves a clicked dot when the jump is clamped near the bottom (scrollTop %s)", async (scrollTop) => {
  const mixed = [steps[0], { ...steps[1], role: "user" }, steps[2]] as RmStep[];
  const container = document.createElement("div");
  container.innerHTML = '<div><div id="step-0"></div><div id="step-1"></div><div id="step-2"></div></div>';
  Object.defineProperties(container, { scrollHeight: { value: 1000 }, clientHeight: { value: 500 } });
  container.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
  const header = document.createElement("div");
  header.getBoundingClientRect = () => ({ bottom: 100 }) as DOMRect;
  for (const [index, element] of [...container.querySelectorAll<HTMLElement>("[id]")].entries()) {
    element.getBoundingClientRect = () => ({ top: [100, 220, 350][index] }) as DOMRect;
    element.getClientRects = () => [element.getBoundingClientRect()] as unknown as DOMRectList;
  }
  const props = { annotations: [], scroller: { current: container }, navigation: { current: header }, onJump: () => {
    container.scrollTop = scrollTop;
    fireEvent.scroll(container);
  } };
  const { rerender } = render(<TraceMinimap steps={mixed} {...props} />);
  const user = screen.getByRole("button", { name: "Step 2: User" });
  fireEvent.pointerDown(user.querySelector("[data-zero-marker]")!, { pointerId: 1, button: 0 });
  fireEvent.pointerUp(user, { pointerId: 1 });
  await act(async () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(user).toHaveAttribute("aria-current", "step");
  // Polling replaces step objects but must not discard the explicit selection.
  rerender(<TraceMinimap steps={mixed.map((step) => ({ ...step }))} {...props} />);
  await act(async () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  expect(user).toHaveAttribute("aria-current", "step");
  fireEvent.wheel(container);
  container.scrollTop = 500;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByText("Step 3 of 3")).toBeVisible());
});

it("explains why each unscored step lacks a grade", () => {
  const mixed = [steps[0], { ...steps[1], role: "user", content: "Please fix the duplicate notifications.", metadata: { timestamp: "2026-10-08T00:46:47Z" } }, steps[2]] as RmStep[];
  render(<TraceMinimap steps={mixed} annotations={[]} actionScores={new Map([["2", { step_id: "2", credit: 0.1 } as RmActionScore]])} unscoredReasons={new Map([["0", "insufficient evidence"]])} scroller={{ current: null }} navigation={{ current: null }} onJump={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Step 1: Response, insufficient evidence" })).toBeVisible();
  const user = screen.getByRole("button", { name: "Step 2: User" });
  expect(user).toBeVisible();
  fireEvent.focus(user);
  const tooltip = screen.getByRole("tooltip");
  expect(tooltip).toHaveTextContent("(2)");
  expect(tooltip.querySelector("time")).toHaveAttribute("dateTime", "2026-10-08T00:46:47Z");
  expect(tooltip).toHaveTextContent("Please fix the duplicate notifications.");
  expect(tooltip).not.toHaveTextContent(/not graded|awaiting score/);
  expect(user.querySelector("[data-zero-marker]")).toHaveClass("h-px");
  expect(user.querySelector("[data-zero-marker]")).not.toHaveClass("rounded-full");
  expect(user.lastElementChild).toHaveStyle({ height: "0%" });
  expect(screen.getByRole("button", { name: "Step 1: Response, insufficient evidence" }).querySelector("[data-zero-marker]")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Step 3: Response, credit +0.10" })).toBeVisible();
});

it("immediately shows scores and statuses on hover without jumping or relying on native titles", () => {
  const onJump = vi.fn();
  renderMap(steps, onJump, new Map([["0", { step_id: "0", credit: 0.35 } as RmActionScore]]));
  const map = screen.getByRole("group", { name: "Step map" });
  map.getBoundingClientRect = () => ({ left: 100, width: 300 }) as DOMRect;
  expect(screen.getByRole("button", { name: "Step 1: Response, credit +0.35" })).not.toHaveAttribute("title");
  fireEvent.pointerEnter(map, { pointerType: "mouse", clientX: 110 });
  expect(screen.getByRole("tooltip")).toHaveTextContent("(1)ResponseCredit +0.35");
  fireEvent.pointerMove(map, { pointerType: "mouse", clientX: 250 });
  expect(screen.getByRole("tooltip")).toHaveTextContent("(2)Responseawaiting score");
  expect(onJump).not.toHaveBeenCalled();
  fireEvent.pointerLeave(map);
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
});

it("shows the tooltip on keyboard focus and dismisses it on Escape or blur", () => {
  renderMap();
  const bar = screen.getByRole("button", { name: "Step 1: Response, credit +0.25" });
  fireEvent.focus(bar);
  expect(screen.getByRole("tooltip")).toHaveTextContent("(1)ResponseCredit +0.25");
  fireEvent.keyDown(bar, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  fireEvent.focus(bar);
  fireEvent.blur(bar);
  expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
});


it("keeps ungraded traces navigable without score heights and retains previous grades", () => {
  const props = { steps, annotations: [], scroller: { current: null }, navigation: { current: null }, onJump: vi.fn() };
  const { rerender } = render(<TraceMinimap {...props} actionScores={new Map()} />);
  expect(screen.getByRole("navigation", { name: "Trace steps" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Step 2: Response, awaiting score" }).lastElementChild).toHaveStyle({ height: "0%" });
  const saved = new Map([["0", { step_id: "0", credit: 0.25, stale: true } as RmActionScore]]);
  rerender(<TraceMinimap {...props} actionScores={saved} annotationStatus="Updating annotations" />);
  expect(screen.getByRole("button", { name: "Step 1: Response, credit +0.25, previous annotation" }).lastElementChild).toHaveStyle({ height: "12.5%", bottom: "50%" });
  expect(screen.getByRole("group", { name: "Step map" })).toBeVisible();
});
