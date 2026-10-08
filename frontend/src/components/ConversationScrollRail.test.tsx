import { createRef } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ConversationScrollRail, { conversationMarkers } from "./ConversationScrollRail";

const items = conversationMarkers([
  { targetId: "first", role: "user", content: "Check the tests" },
  { targetId: "reply", role: "assistant", content: "**All checks pass.**" },
  { targetId: "second", role: "user", content: "Review the diff" },
  { targetId: "third", role: "user", content: "Ship it" },
]);

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("CSS", { escape: (id: string) => id });
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function setup() {
  const scroller = createRef<HTMLDivElement>();
  const header = createRef<HTMLDivElement>();
  const result = render(<div>
    <ConversationScrollRail items={items} scroller={scroller} header={header} />
    <div ref={scroller}><div ref={header} />{items.map((item) => <div key={item.targetId} id={item.targetId}>{item.title}</div>)}</div>
  </div>);
  const container = scroller.current!;
  Object.defineProperties(container, { clientHeight: { value: 400 }, scrollHeight: { value: 1600 } });
  Object.defineProperty(header.current, "offsetHeight", { value: 100 });
  container.scrollTo = vi.fn();
  container.getBoundingClientRect = () => ({ top: 50 }) as DOMRect;
  items.forEach((item, index) => {
    const target = container.querySelector<HTMLElement>(`#${item.targetId}`)!;
    target.getBoundingClientRect = () => ({ top: 50 + index * 600 - container.scrollTop }) as DOMRect;
    target.getClientRects = () => [target.getBoundingClientRect()] as unknown as DOMRectList;
  });
  // Re-render after jsdom's missing layout has been supplied.
  result.rerender(<div>
    <ConversationScrollRail items={[...items]} scroller={scroller} header={header} />
    <div ref={scroller}><div ref={header} />{items.map((item) => <div key={item.targetId} id={item.targetId}>{item.title}</div>)}</div>
  </div>);
  return container;
}

it("previews the prompt and reply, and jumps within its pane below the sticky header", () => {
  const container = setup();
  const first = screen.getByRole("button", { name: "Message 1: Check the tests" });
  fireEvent.mouseEnter(first);
  expect(screen.getByRole("tooltip")).toHaveTextContent("All checks pass.");
  fireEvent.mouseLeave(screen.getByRole("navigation"));
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Message 2: Review the diff" }));
  expect(container.scrollTo).toHaveBeenCalledWith({ top: 488, behavior: "instant" });
});

it("tracks manual scrolling through the last short exchange", async () => {
  const container = setup();
  container.scrollTop = 650;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Message 2: Review the diff" })).toHaveAttribute("aria-current", "location"));
  container.scrollTop = 1200;
  fireEvent.scroll(container);
  await waitFor(() => expect(screen.getByRole("button", { name: "Message 3: Ship it" })).toHaveAttribute("aria-current", "location"));
});

it("lets the keyboard browse previews without jumping until activation", () => {
  const container = setup();
  const first = screen.getByRole("button", { name: "Message 1: Check the tests" });
  fireEvent.keyDown(first, { key: "ArrowDown" });
  const second = screen.getByRole("button", { name: "Message 2: Review the diff" });
  expect(second).toHaveFocus();
  expect(screen.getByRole("tooltip")).toHaveTextContent("Review the diff");
  expect(container.scrollTo).not.toHaveBeenCalled();
  fireEvent.keyDown(second, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
});

it("scrubs immediately in both directions, clamps at the ends, and stops on release", () => {
  const container = setup();
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  const scrubber = screen.getByRole("group", { name: "Conversation scrubber" });
  scrubber.getBoundingClientRect = () => ({ top: 100, bottom: 400, height: 300, left: 0, right: 32 }) as DOMRect;
  const capture = vi.spyOn(scrubber, "setPointerCapture");
  const second = screen.getByRole("button", { name: "Message 2: Review the diff" });

  fireEvent.pointerDown(scrubber, { pointerId: 1, button: 0, clientY: 110 });
  expect(capture).toHaveBeenCalledWith(1);
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 250 });
  expect(second).toHaveFocus();
  expect(second).toHaveAttribute("aria-current", "location");
  expect(screen.getByRole("tooltip")).toHaveTextContent("Review the diff");
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 260 });
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 500 });
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 50 });
  fireEvent.pointerUp(scrubber, { pointerId: 1, clientY: 50 });
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 350 });
  // A drag's synthesized click must not jump back to the starting button.
  fireEvent.click(second, { detail: 1 });
  expect(container.scrollTo).toHaveBeenCalledTimes(4);
  expect(vi.mocked(container.scrollTo).mock.calls).toEqual([
    [{ top: -112, behavior: "instant" }],
    [{ top: 488, behavior: "instant" }],
    [{ top: 1088, behavior: "instant" }],
    [{ top: -112, behavior: "instant" }],
  ]);
  expect(screen.queryByRole("tooltip")).toBeNull();
});

it.each(["pointerCancel", "lostPointerCapture"] as const)("stops scrubbing on %s and keeps keyboard activation", (endEvent) => {
  const onJump = vi.fn();
  render(<ConversationScrollRail items={items} scroller={{ current: null }} onJump={onJump} />);
  const scrubber = screen.getByRole("group", { name: "Conversation scrubber" });
  scrubber.getBoundingClientRect = () => ({ top: 100, height: 300 }) as DOMRect;
  fireEvent.pointerDown(scrubber, { pointerId: 1, button: 2, clientY: 110 });
  expect(onJump).not.toHaveBeenCalled();
  fireEvent.pointerDown(scrubber, { pointerId: 1, button: 0, pointerType: "touch", clientY: 110 });
  fireEvent.pointerMove(scrubber, { pointerId: 2, clientY: 350 });
  fireEvent[endEvent](scrubber, { pointerId: 1 });
  fireEvent.pointerMove(scrubber, { pointerId: 1, clientY: 350 });
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Message 3: Ship it" }), { detail: 0 });
  expect(onJump.mock.calls).toEqual([[items[0]], [items[2]]]);
});
