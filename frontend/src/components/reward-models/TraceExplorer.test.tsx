import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import TraceExplorer from "./TraceExplorer";
import { buildTraceOutline } from "./trace-outline";
import { presentTrace } from "./trace-presentation";
import type { RmStep } from "@/lib/types";
import type { StepAnnotations } from "./TraceTimeline";
import { rmSummarizeSections } from "@/lib/api";

vi.mock("@/lib/api", () => ({ rmSummarizeSections: vi.fn() }));
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("PointerEvent", MouseEvent);
  vi.mocked(rmSummarizeSections).mockImplementation(async (_, sections) => ({
    sections: sections.map((range, i) => ({ ...range, title: `Checking site ${i + 1}`, summary: "Looks up and verifies the available parts.", objective: "Find the requested part", score: 0.82, score_reason: "The catalog matches the requested specification." })), pending: false, unavailable: false,
  }));
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const ann: StepAnnotations = { highlights: () => [], commentCount: () => 0, hasQuotes: () => false, flashing: () => false, onComment: vi.fn(), onSelectAnnotation: vi.fn() };
const rows = presentTrace(Array.from({ length: 48 }, (_, i): RmStep => ({ id: `s${i}`, index: i, role: i % 12 ? "assistant" : "user", content: `Task ${i}`, tool_name: null, tool_input: null, tool_call_id: null, metadata: null }))).rows;
const groups = buildTraceOutline(rows);
function Harness({ opened = vi.fn() }: { opened?: () => void }) {
  const [path, setPath] = useState<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  return <div ref={scroller}><TraceExplorer traceId="t1" groups={groups} path={path} onPath={setPath} ann={ann} isExpanded={() => false} onToggle={vi.fn()} onOpenRows={opened} scroller={scroller} /></div>;
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

it("opens on deliberate hover, cancels when leaving, and does not cascade without pointer movement", async () => {
  const opened = vi.fn();
  render(<Harness opened={opened} />);
  await load();
  let button = screen.getAllByRole("button", { name: /^Explore / })[0];
  mouseMove(button);
  act(() => vi.advanceTimersByTime(200));
  fireEvent.pointerLeave(button);
  act(() => vi.advanceTimersByTime(500));
  expect(screen.queryByRole("button", { name: "Zoom out" })).not.toBeInTheDocument();
  mouseMove(button);
  await act(async () => vi.advanceTimersByTime(450));
  expect(screen.getByRole("button", { name: "Zoom out" })).toBeInTheDocument();
  const count = screen.getAllByRole("button", { name: /^Explore / }).length;
  await act(async () => vi.advanceTimersByTime(5000));
  expect(screen.getAllByRole("button", { name: /^Explore / })).toHaveLength(count);
  button = screen.getAllByRole("button", { name: /^Explore / })[0];
  mouseMove(button);
  await act(async () => vi.advanceTimersByTime(450));
  expect(opened).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: /^Explore / })).not.toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("region", { name: "Trace explorer" }), { key: "Escape" });
  await load();
  expect(screen.getAllByRole("button", { name: /^Explore / }).length).toBeGreaterThan(0);
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
