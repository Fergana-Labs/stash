import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import TraceExplorer from "./TraceExplorer";
import { buildTraceOutline, groupPath, traceExplorerLevel, tracePhases } from "./trace-outline";
import { presentTrace } from "./trace-presentation";
import type { RmStep } from "@/lib/types";
import type { StepAnnotations } from "./TraceTimeline";
import { rmSummarizeSections } from "@/lib/api";
import { useSectionSummaries } from "./use-section-summaries";
import TraceScrollRail from "./TraceScrollRail";
import { rowSteps } from "./trace-rows";
import { traceSectionTarget } from "./trace-scroll";

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
function Harness({ outline = groups }: { outline?: ReturnType<typeof buildTraceOutline> }) {
  const [path, setPath] = useState<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const { trail, current, children: sections } = traceExplorerLevel(outline, path);
  const assessments = useSectionSummaries("t1", [...new Map([...sections, ...trail, ...outline, ...(current && !sections.length ? tracePhases(outline).map(({ node }) => node) : [])].map((node) => [node.key, node])).values()]);
  return <div>
    <TraceScrollRail groups={outline} path={path} rows={outline.flatMap((group) => group.rows)} copy={assessments.copy} stepNumber={(step) => step.index + 1} scroller={scroller} onPath={setPath} onStep={(id) => setPath(groupPath(outline, id))} />
    <div ref={scroller} data-trace-scroll><TraceExplorer groups={outline} path={path} onPath={setPath} assessments={assessments} ann={ann} isExpanded={() => false} onToggle={vi.fn()} /></div>
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
  fireEvent.click(screen.getByRole("button", { name: "Back to sections" }));
  await load();
  expect(rmSummarizeSections).toHaveBeenCalledTimes(2);
  expect(screen.getAllByRole("button", { name: /^Explore Checking site/ })).toHaveLength(4);
});

it("leaves context-only sections ungraded even when the API returns a numeric score", async () => {
  const contextSteps: RmStep[] = ["system", "user", "tool", "assistant"].map((role, index) => ({
    id: `context-${index}`, index, role: role as RmStep["role"], content: "Supplied context",
    tool_name: null, tool_input: null, tool_call_id: null, metadata: role === "assistant" ? { thinking: true } : null,
  }));
  const work = { ...contextSteps[3], id: "action", index: 4, metadata: null, content: "I verified the order." };
  render(<Harness outline={[
    { key: "context", rows: presentTrace(contextSteps).rows, children: [] },
    { key: "work", rows: presentTrace([work]).rows, children: [] },
  ]} />);
  expect(screen.getByLabelText("Ungraded context for Steps 1–4")).toHaveTextContent("Ungraded");
  await load();
  expect(screen.queryByRole("button", { name: /Section score .* for Steps 1–4/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Ungraded context for Steps 1–4")).toHaveTextContent("Ungraded");
  expect(screen.getByRole("button", { name: "Section score 0.82 for Step 5" })).toBeVisible();
});

it("only makes ancestor breadcrumbs clickable", async () => {
  render(<Harness />);
  await load();
  expect(screen.queryByRole("navigation", { name: "Trace hierarchy" })).not.toBeInTheDocument();
  expect(screen.queryByText("Sections", { exact: true })).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore / })[0]);
  await load();
  const hierarchy = screen.getByRole("navigation", { name: "Trace hierarchy" });
  const current = hierarchy.querySelector('[aria-current="location"]')!;
  expect(current.tagName).toBe("SPAN");
  expect(current.closest("button")).toBeNull();
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore / })[0]);
  await load();
  // The parent now leads somewhere; the final breadcrumb remains plain text.
  fireEvent.click(within(hierarchy).getByRole("button", { name: "Checking site 1" }));
  await load();
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(2);
});

it.each([["Enter", "Escape"], ["ArrowRight", "ArrowLeft"]])("uses Up/Down to select, %s to open, and %s to return", async (openKey, backKey) => {
  render(<Harness />);
  await load();
  const original = screen.getAllByRole("button", { name: /^Explore / });
  expect(original[0]).toHaveAttribute("aria-current", "true");
  fireEvent.keyDown(document.body, { key: "ArrowDown" });
  expect(original[1]).toHaveFocus();
  expect(original[1]).toHaveAttribute("aria-current", "true");
  fireEvent.keyDown(original[1], { key: openKey });
  await load();
  await act(async () => vi.advanceTimersByTime(16));
  let children = screen.getAllByRole("button", { name: /^Explore / });
  expect(children[0]).toHaveFocus();
  fireEvent.keyDown(children[0], { key: openKey, repeat: true });
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(children.length);
  fireEvent.keyDown(children[0], { key: openKey });
  expect(screen.queryByRole("button", { name: /^Collapse .* message$/ })).not.toBeInTheDocument();
  // Entering a subsection opens a continuous reader with each step present once.
  for (const row of rows) expect(screen.getAllByLabelText(`Step ${rowSteps(row)[0].index + 1}`)).toHaveLength(1);
  expect(document.querySelectorAll("[data-trace-phase]")).toHaveLength(tracePhases(groups).length);
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: backKey, repeat: true });
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  fireEvent.keyDown(document.body, { key: backKey });
  await load();
  fireEvent.keyDown(document.body, { key: backKey });
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
  expect(screen.queryByRole("button", { name: "Back to sections" })).not.toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Comment" }), { key: "Enter" });
  fireEvent.keyDown(screen.getByRole("button", { name: "Outside control" }), { key: "Enter" });
  expect(screen.queryByRole("button", { name: "Back to sections" })).not.toBeInTheDocument();
});

it("remains navigable if generation is unavailable", async () => {
  vi.mocked(rmSummarizeSections).mockRejectedValue(new Error("Offline"));
  render(<Harness />);
  await load();
  expect(screen.getByRole("status")).toHaveTextContent("Section assessments unavailable");
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore / })[0]);
  await load();
  expect(screen.getByRole("button", { name: "Back to sections" })).toBeInTheDocument();
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

it("keeps global markers through nested navigation and scrubs between tasks without losing keyboard focus", async () => {
  const measurements = new Set<() => void>();
  vi.stubGlobal("ResizeObserver", class {
    constructor(private callback: () => void) { measurements.add(callback); }
    observe() {}
    disconnect() { measurements.delete(this.callback); }
  });
  render(<Harness />);
  await load();
  let cards = screen.getAllByRole("button", { name: /^Explore / });
  const container = screen.getByRole("region", { name: "Trace explorer" }).parentElement!;
  container.scrollTo = vi.fn();
  async function scrollToTask(index: number) {
    container.scrollTop = index * 500;
    groups.forEach((group, i) => {
      const target = document.getElementById(traceSectionTarget(group));
      if (!target) return;
      target.getBoundingClientRect = () => ({ top: 150 + i * 500 - container.scrollTop }) as DOMRect;
      target.getClientRects = () => [target.getBoundingClientRect()] as unknown as DOMRectList;
    });
    tracePhases(groups).forEach(({ node, path }) => {
      const taskIndex = groups.findIndex((group) => group.key === path[0]);
      const phaseIndex = groups[taskIndex].children.indexOf(node);
      const target = document.getElementById(traceSectionTarget(node));
      if (!target) return;
      target.getBoundingClientRect = () => ({ top: 150 + taskIndex * 500 + Math.max(0, phaseIndex) * 200 - container.scrollTop }) as DOMRect;
      target.getClientRects = () => [target.getBoundingClientRect()] as unknown as DOMRectList;
    });
    act(() => measurements.forEach((measure) => measure()));
    fireEvent.scroll(container);
    await act(async () => vi.advanceTimersByTime(16));
  }
  container.getBoundingClientRect = () => ({ top: 150 }) as DOMRect;
  cards[1].parentElement!.getBoundingClientRect = () => ({ top: 600 }) as DOMRect;
  const rail = screen.getByRole("navigation", { name: "Conversation navigation" });
  const markers = Array.from(rail.querySelectorAll("button"));
  const labels = markers.map((marker) => marker.getAttribute("aria-label"));
  const scrubber = screen.getByRole("group", { name: "Conversation scrubber" });
  scrubber.getBoundingClientRect = () => ({ top: 0, height: 400 }) as DOMRect;
  fireEvent.pointerDown(scrubber, { button: 0, clientY: 150 });
  fireEvent.pointerUp(scrubber, { button: 0, clientY: 150 });
  await act(async () => vi.advanceTimersByTime(16));
  expect(cards[1]).toHaveFocus();
  expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 410, behavior: "instant" });
  fireEvent.keyDown(cards[1], { key: "Enter" });
  await load();
  cards = screen.getAllByRole("button", { name: /^Explore / });
  expect(cards).toHaveLength(2);
  expect(rail.querySelectorAll("button")).toHaveLength(4);
  expect(markers[1]).toHaveAttribute("aria-current", "location");
  fireEvent.keyDown(cards[1], { key: "Enter" });
  await load();
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  await scrollToTask(1);
  expect(markers[1]).toHaveAttribute("aria-current", "location");
  // Scrolling into another task updates the active marker without replacing the reader.
  const firstMessage = document.getElementById("step-s0");
  await scrollToTask(2);
  expect(document.getElementById("step-s0")).toBe(firstMessage);
  expect(container.scrollTop).toBe(1000);
  expect(markers[2]).toHaveAttribute("aria-current", "location");
  expect(Array.from(rail.querySelectorAll("button"))).toEqual(markers);
  expect(markers.map((marker) => marker.getAttribute("aria-label"))).toEqual(labels);

  // Drag across tasks while deep in a subsection. The rail must not remount or
  // change scale partway through the drag, and each destination stays global.
  fireEvent.pointerDown(scrubber, { button: 0, clientY: 250 });
  await load();
  fireEvent.pointerMove(scrubber, { clientY: 350 });
  fireEvent.pointerUp(scrubber, { clientY: 350 });
  await load();
  await act(async () => vi.advanceTimersByTime(16));
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(2);
  expect(markers[3]).toHaveAttribute("aria-current", "location");
  expect(screen.getByRole("region", { name: "Trace explorer" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Enter" });
  await load();
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  await scrollToTask(3);
  expect(markers[3]).toHaveAttribute("aria-current", "location");
  fireEvent.click(markers[0]);
  await load();
  await act(async () => vi.advanceTimersByTime(16));
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(4);
  expect(container.scrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: "instant" });
  await scrollToTask(0);
  expect(markers[0]).toHaveAttribute("aria-current", "location");
});

it("retains all step destinations for a single task while browsing its subsections", async () => {
  render(<Harness outline={[groups[0]]} />);
  await load();
  const rail = screen.getByRole("navigation", { name: "Conversation navigation" });
  const markers = Array.from(rail.querySelectorAll("button"));
  expect(markers).toHaveLength(12);
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(2);
  fireEvent.click(screen.getAllByRole("button", { name: /^Explore / })[1]);
  await load();
  expect(Array.from(rail.querySelectorAll("button"))).toEqual(markers);
  fireEvent.click(markers[3]);
  await load();
  expect(document.getElementById("step-s3")).toBeInTheDocument();
  expect(Array.from(rail.querySelectorAll("button"))).toEqual(markers);
});


it("opens a single task on its subtasks immediately, before assessment requests finish", async () => {
  vi.mocked(rmSummarizeSections).mockImplementation(() => new Promise(() => {}));
  render(<Harness outline={[groups[0]]} />);
  const cards = screen.getAllByRole("button", { name: /^Explore / });
  expect(cards).toHaveLength(2);
  expect(cards[0]).toHaveAccessibleName("Explore Task 1");
  expect(cards[1]).toHaveAccessibleName("Explore Task 7");
  expect(screen.queryByRole("button", { name: "Back to sections" })).not.toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Trace hierarchy" })).toHaveTextContent("Task 1");
  fireEvent.keyDown(document.body, { key: "ArrowDown" });
  fireEvent.keyDown(document.activeElement!, { key: "Enter" });
  await act(async () => vi.advanceTimersByTime(16));
  expect(document.getElementById("step-s7")).toBeInTheDocument();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  await act(async () => vi.advanceTimersByTime(16));
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Explore Task 7" })).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(2);
});

it("opens a single continuous task directly on its steps", async () => {
  const outline = buildTraceOutline(presentTrace(Array.from({ length: 20 }, (_, i): RmStep => ({ id: `continuous${i}`, index: i, role: i ? "assistant" : "user", content: `Message ${i}`, tool_name: null, tool_input: null, tool_call_id: null, metadata: null }))).rows);
  render(<Harness outline={outline} />);
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  expect(document.getElementById("step-continuous19")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Back to sections" })).not.toBeInTheDocument();
  await load();
});
