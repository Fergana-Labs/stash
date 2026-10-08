import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import TraceExplorer from "./TraceExplorer";
import { buildTraceOutline, resolveGroupPath } from "./trace-outline";
import { presentTrace } from "./trace-presentation";
import type { RmStep } from "@/lib/types";
import type { StepAnnotations } from "./TraceTimeline";
import { rmSummarizeSections } from "@/lib/api";
import { useSectionSummaries } from "./use-section-summaries";
import TraceScrollRail from "./TraceScrollRail";

vi.mock("@/lib/api", () => ({ rmSummarizeSections: vi.fn() }));
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.stubGlobal("CSS", { escape: (id: string) => id });
  vi.mocked(rmSummarizeSections).mockImplementation(async (_, sections) => ({
    sections: sections.map((range, i) => ({ ...range, title: `Checking site ${i + 1}`, summary: "Looks up and verifies the available parts.", objective: "Find the requested part", score: 0.82, score_reason: "The catalog matches the requested specification." })), pending: false, unavailable: false,
  }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const ann: StepAnnotations = { highlights: () => [], commentCount: () => 0, hasQuotes: () => false, flashing: () => false, onComment: vi.fn(), onSelectAnnotation: vi.fn() };
const rows = presentTrace(Array.from({ length: 48 }, (_, i): RmStep => ({ id: `s${i}`, index: i, role: i % 12 ? "assistant" : "user", content: `Task ${i}`, tool_name: null, tool_input: null, tool_call_id: null, metadata: i % 12 === 1 || i % 12 === 7 ? { phase: "commentary" } : null }))).rows;
const groups = buildTraceOutline(rows);
function Harness({ opened = vi.fn(), outline = groups }: { opened?: () => void; outline?: ReturnType<typeof buildTraceOutline> }) {
  const [path, setPath] = useState<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const current = resolveGroupPath(outline, path).at(-1);
  const direct = !path.length && outline.length === 1 && !outline[0].children.length && outline[0].rows.length <= 8;
  const sections = direct ? [] : current?.children ?? outline;
  const assessments = useSectionSummaries("t1", sections);
  return <div>
    <TraceScrollRail key={path.join("/")} sections={sections} rows={current?.rows ?? outline.flatMap((group) => group.rows)} copy={assessments.copy} stepNumber={(step) => step.index + 1} scroller={scroller} />
    <div ref={scroller}><TraceExplorer groups={outline} path={path} onPath={setPath} assessments={assessments} ann={ann} isExpanded={() => false} onToggle={vi.fn()} onOpenRows={opened} /></div>
  </div>;
}
async function load() { await act(async () => { await Promise.resolve(); }); }
function mouseMove(element: HTMLElement) {
  const event = new MouseEvent("pointermove", { bubbles: true });
  Object.defineProperty(event, "pointerType", { value: "mouse" });
  fireEvent(element, event);
}

it("replaces request excerpts with generated titles and reuses them on return", async () => {
  render(<Harness />);
  await load();
  expect(screen.getAllByRole("button", { name: /^Explore Checking site/ })).toHaveLength(4);
  expect(screen.queryByText("Task 0")).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore / })[0]);
  await load();
  fireEvent.click(screen.getByRole("button", { name: "Overview" }));
  await load();
  expect(rmSummarizeSections).toHaveBeenCalledTimes(2);
  expect(screen.getAllByRole("button", { name: /^Explore Checking site/ })).toHaveLength(4);
});

it("navigates with arrows, expands leaf steps, and restores selection when going back", async () => {
  const opened = vi.fn();
  render(<Harness opened={opened} />);
  await load();
  const original = screen.getAllByRole("button", { name: /^Explore / });
  expect(original[0]).toHaveAttribute("aria-current", "true");
  fireEvent.keyDown(document.body, { key: "ArrowDown" });
  expect(original[1]).toHaveFocus();
  expect(original[1]).toHaveAttribute("aria-current", "true");
  fireEvent.keyDown(original[1], { key: "ArrowRight" });
  await load();
  await act(async () => vi.advanceTimersByTime(16));
  let children = screen.getAllByRole("button", { name: /^Explore / });
  expect(children[0]).toHaveFocus();
  fireEvent.keyDown(children[0], { key: "ArrowRight", repeat: true });
  expect(opened).not.toHaveBeenCalled();
  fireEvent.keyDown(children[0], { key: "ArrowRight" });
  expect(opened).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  await load();
  fireEvent.keyDown(document.body, { key: "ArrowLeft" });
  await load();
  await act(async () => vi.advanceTimersByTime(16));
  children = screen.getAllByRole("button", { name: /^Explore / });
  expect(children[1]).toHaveFocus();
  expect(children[1]).toHaveAttribute("aria-current", "true");
  fireEvent.keyDown(children[1], { key: "ArrowUp" });
  expect(children[0]).toHaveFocus();
});

it("uses mouse hover only to select and leaves editing and other controls alone", async () => {
  render(<><Harness /><input aria-label="Comment" /><button>Outside control</button></>);
  await load();
  const buttons = screen.getAllByRole("button", { name: /^Explore / });
  mouseMove(buttons[2]);
  expect(buttons[2]).toHaveAttribute("aria-current", "true");
  expect(screen.queryByRole("button", { name: "Zoom out" })).not.toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Comment" }), { key: "ArrowRight" });
  fireEvent.keyDown(screen.getByRole("button", { name: "Outside control" }), { key: "ArrowRight" });
  expect(screen.queryByRole("button", { name: "Zoom out" })).not.toBeInTheDocument();
});

it("remains navigable if generation is unavailable", async () => {
  vi.mocked(rmSummarizeSections).mockRejectedValue(new Error("Offline"));
  render(<Harness />);
  await load();
  expect(screen.getByRole("status")).toHaveTextContent("Section assessments unavailable");
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore Steps / })[0]);
  await load();
  expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
});


it("keeps more than four sections visible in the list and batches their assessments", async () => {
  const outline = buildTraceOutline(presentTrace(Array.from({ length: 18 }, (_, i): RmStep => ({ id: `many${i}`, index: i, role: i % 2 ? "assistant" : "user", content: `Request ${i}`, tool_name: null, tool_input: null, tool_call_id: null, metadata: null }))).rows);
  render(<Harness outline={outline} />);
  await load();
  expect(screen.getAllByRole("button", { name: /^Explore Checking site/ })).toHaveLength(9);
  const batches = vi.mocked(rmSummarizeSections).mock.calls.map(([, batch]) => batch);
  expect(batches.map((batch) => batch.length)).toEqual([4, 4, 1]);
  expect(new Set(batches.flat().map((range) => range.first_step_id)).size).toBe(9);
});

it("scrubs only the visible level and lets arrow navigation continue from the scrubbed section", async () => {
  const opened = vi.fn();
  render(<Harness opened={opened} />);
  await load();
  let cards = screen.getAllByRole("button", { name: /^Explore / });
  const container = screen.getByRole("region", { name: "Trace explorer" }).parentElement!;
  container.scrollTo = vi.fn();
  container.getBoundingClientRect = () => ({ top: 150 }) as DOMRect;
  cards[1].parentElement!.getBoundingClientRect = () => ({ top: 600 }) as DOMRect;
  const scrubber = screen.getByRole("group", { name: "Conversation scrubber" });
  scrubber.getBoundingClientRect = () => ({ top: 0, height: 400 }) as DOMRect;
  fireEvent.pointerDown(scrubber, { button: 0, clientY: 150 });
  fireEvent.pointerUp(scrubber, { button: 0, clientY: 150 });
  expect(cards[1]).toHaveFocus();
  expect(cards[1]).toHaveAttribute("aria-current", "true");
  expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 438, behavior: "instant" });
  expect(screen.queryByRole("button", { name: "Zoom out" })).not.toBeInTheDocument();
  expect(opened).not.toHaveBeenCalled();
  fireEvent.keyDown(cards[1], { key: "ArrowRight" });
  await load();
  cards = screen.getAllByRole("button", { name: /^Explore / });
  const rail = screen.getByRole("navigation", { name: "Conversation navigation" });
  expect(rail.querySelectorAll("button")).toHaveLength(cards.length);
  fireEvent.click(rail.querySelectorAll("button")[0]);
  expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: "instant" });
  expect(cards[0]).toHaveFocus();
  fireEvent.keyDown(cards[0], { key: "ArrowRight" });
  await load();
  const leafRail = screen.getByRole("navigation", { name: "Conversation navigation" });
  fireEvent.click(leafRail.querySelectorAll("button")[1]);
  expect(screen.getByRole("region", { name: "Trace explorer" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
  await load();
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(cards.length);
});
