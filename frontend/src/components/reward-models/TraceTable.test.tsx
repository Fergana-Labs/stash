import { useState } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import TraceTable from "./TraceTable";

const { push, search, rename } = vi.hoisted(() => ({ push: vi.fn(), search: vi.fn(), rename: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmListAllTraces: search, rmRenameTraceSource: rename }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });

const traces: RmTraceSummary[] = [20, 3, 10].map((steps) => ({
  id: String(steps), title: `Trace ${steps}`, step_count: steps,
  external_id: null, source_format: "otel", positive_count: 0, negative_count: 0,
  comment_count: 0, label_error_count: 0, latest_score: null, created_at: "2026-09-29T00:00:00Z",
}));

function Table({ mode = "browse" }: { mode?: "browse" | "picker" }) {
  const [selected, setSelected] = useState(new Set(["20"]));
  return <TraceTable traces={traces} selected={selected} onSelectedChange={setSelected} mode={mode} />;
}

it("sorts browse rows while keeping selection checkboxes available", () => {
  render(<Table />);
  const order = () => screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("link").textContent);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  expect(order()).toEqual(["Trace 3", "Trace 10", "Trace 20"]);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  expect(order()).toEqual(["Trace 20", "Trace 10", "Trace 3"]);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", "descending");
  expect(screen.getByRole("checkbox", { name: "Select all shown traces" })).toBeVisible();
  expect(screen.queryByRole("textbox", { name: "Search titles and trace content" })).not.toBeInTheDocument();
});

it("opens a trace from its non-title cells", () => {
  render(<Table />);
  fireEvent.click(screen.getByRole("cell", { name: "20" }));
  expect(push).toHaveBeenCalledWith("/reward-models/traces/20");
});

it.each(["ascending", "descending"])("restores %s step-count sorting after returning from a trace", (direction) => {
  const view = render(<Table />);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  if (direction === "descending") fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  fireEvent.click(screen.getByRole("cell", { name: "20" }));
  view.unmount();
  render(<Table />);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", direction);
  expect(screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("link").textContent))
    .toEqual(direction === "ascending" ? ["Trace 3", "Trace 10", "Trace 20"] : ["Trace 20", "Trace 10", "Trace 3"]);
});

it("keeps picker sort preferences separate from the browse list", () => {
  const browse = render(<Table />);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  browse.unmount();
  const picker = render(<Table mode="picker" />);
  expect(screen.getByRole("columnheader", { name: "Imported" })).toHaveAttribute("aria-sort", "descending");
  fireEvent.click(screen.getByRole("button", { name: "Trace" }));
  picker.unmount();
  render(<Table />);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", "ascending");
});

it.each(['not json', '{"key":"unknown","direction":"ascending"}'])("ignores invalid saved sorting: %s", (saved) => {
  localStorage.setItem("stash-traces-sort:browse", saved);
  render(<Table />);
  expect(screen.getByRole("columnheader", { name: "Imported" })).toHaveAttribute("aria-sort", "descending");
});

it("keeps deletion separate from opening the trace", () => {
  const onDelete = vi.fn();
  const onSelectedChange = vi.fn();
  render(<TraceTable traces={[traces[0]]} selected={new Set()} onSelectedChange={onSelectedChange} mode="browse" onDelete={onDelete} />);
  expect(screen.getByRole("checkbox", { name: "Select all shown traces" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Delete trace" }).querySelector("svg")!);
  expect(onDelete).toHaveBeenCalledWith(traces[0]);
  expect(push).not.toHaveBeenCalled();
});

it("selects picker rows without leaving the training sheet", () => {
  const onSelectedChange = vi.fn();
  render(<TraceTable traces={traces} selected={new Set()} onSelectedChange={onSelectedChange} mode="picker" />);
  fireEvent.click(screen.getByRole("cell", { name: "20" }));
  expect(onSelectedChange).toHaveBeenCalledWith(new Set(["20"]));
  expect(push).not.toHaveBeenCalled();
});

it("shows automatic annotations separately from learned model scores", () => {
  const trace = { ...traces[0], latest_score: { reward_model_id: "model-1", reward_model_name: "Refund quality", score: 6.011 }, evaluation: { id: "eval", current: true, status: "completed", outcome: "success", total_actions: 5, credited_actions: 5, score: 0.87, action_credit: { mean: 0.25, min: -1, max: 1, count: 5 } } };
  render(<TraceTable traces={[trace]} selected={new Set()} onSelectedChange={vi.fn()} mode="picker" />);
  expect(screen.getByRole("cell", { name: "0.87" })).toBeVisible();
  for (const value of ["0.25", "-1.00", "1.00"]) expect(screen.getByRole("cell", { name: value })).toBeVisible();
  expect(screen.queryByText("Refund quality")).not.toBeInTheDocument();
  expect(screen.queryByText("6.011")).not.toBeInTheDocument();
});

it("shows and sorts comment counts independently of stored ratings", () => {
  const rows = traces.map((trace, i) => ({ ...trace, comment_count: [12, 2, 0][i], positive_count: 7, negative_count: 8 }));
  render(<TraceTable traces={rows} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />);
  expect(screen.queryByRole("columnheader", { name: "Labels" })).not.toBeInTheDocument();
  expect(screen.queryByText("+7")).not.toBeInTheDocument();
  expect(screen.queryByText("−8")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Comments" }));
  expect(screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("link").textContent))
    .toEqual(["Trace 10", "Trace 3", "Trace 20"]);
  expect(screen.getByRole("cell", { name: "12" })).toBeVisible();
});

it("filters scored traces with the Stash dropdown and hides stale annotations", async () => {
  const rows = traces.map((trace, i) => ({ ...trace,
    evaluation: { id: `eval-${i}`, current: i !== 2, status: i === 1 ? "failed" : "completed", outcome: i === 1 ? null : "failure", total_actions: 5, credited_actions: i === 1 ? 0 : 5, score: i === 1 ? null : 0.12 },
  }));
  render(<TraceTable traces={rows} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />);
  expect(screen.getAllByRole("cell", { name: "0.12" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("combobox", { name: "Filter traces" }));
  fireEvent.click(await screen.findByRole("option", { name: "Scored" }));
  expect(screen.getByRole("link", { name: "Trace 20" })).toBeVisible();
  expect(screen.queryByRole("link", { name: "Trace 10" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Trace 3" })).not.toBeInTheDocument();
});

it("finds matches inside content and ignores a late result from an older search", async () => {
  let finishOld!: (value: RmTraceSummary[]) => void;
  search.mockImplementationOnce(() => new Promise((resolve) => { finishOld = resolve; }));
  search.mockResolvedValueOnce([traces[1]]);
  render(<Table mode="picker" />);
  const input = screen.getByRole("textbox", { name: "Search titles and trace content" });
  fireEvent.change(input, { target: { value: "old" } });
  await waitFor(() => expect(search).toHaveBeenCalledWith("old"));
  fireEvent.change(input, { target: { value: "needle in tool output" } });
  await waitFor(() => expect(screen.getByRole("cell", { name: "Trace 3" })).toBeVisible());
  await act(async () => finishOld([traces[0]]));
  expect(screen.queryByRole("cell", { name: "Trace 20" })).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "" } });
  expect(screen.getByRole("cell", { name: "Trace 20" })).toBeVisible();
});

it("filters by source and date, and renames a source without changing its ID", async () => {
  rename.mockResolvedValue({ source_id: "codex", source_name: "Henry’s Codex" });
  const rows = traces.map((trace, i) => ({ ...trace, source_owner_id: "henry", source_id: i === 2 ? "heavi" : "codex", source_name: i === 2 ? "Heavi" : "Codex", created_at: new Date(2026, 9, 7 + i, 12).toISOString() }));
  render(<TraceTable traces={rows} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />);
  fireEvent.click(screen.getByRole("combobox", { name: "Filter by source" }));
  fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
  fireEvent.change(screen.getByLabelText("Imported from"), { target: { value: "2026-10-08" } });
  fireEvent.change(screen.getByLabelText("Imported through"), { target: { value: "2026-10-09" } });
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual(["Trace 3"]);
  fireEvent.click(screen.getByRole("button", { name: "Rename source" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Source name" }), { target: { value: "Henry’s Codex" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(rename).toHaveBeenCalledWith("codex", "Henry’s Codex");
  expect(screen.getByRole("cell", { name: "Henry’s Codex" })).toHaveAttribute("title", "Henry’s Codex · Source ID: codex");
  expect(screen.getByRole("combobox", { name: "Filter by source" })).toHaveTextContent("Henry’s Codex");
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getAllByRole("link")).toHaveLength(3);
  expect(screen.getAllByRole("cell", { name: "Henry’s Codex" })).toHaveLength(2);
});

it("does not offer source renaming for traces shared by another owner", async () => {
  render(<TraceTable traces={[{ ...traces[0], can_score: false }]} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />);
  fireEvent.click(screen.getByRole("combobox", { name: "Filter by source" }));
  fireEvent.click(await screen.findByRole("option", { name: "OpenTelemetry" }));
  expect(screen.queryByRole("button", { name: "Rename source" })).not.toBeInTheDocument();
});


it("shift-selects browse rows in sorted order without navigation", () => {
  render(<Table />);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 3" }));
  fireEvent.click(screen.getByRole("link", { name: "Trace 10" }), { shiftKey: true });
  for (const trace of traces) expect(screen.getByRole("checkbox", { name: `Select ${trace.title}` })).toBeChecked();
  expect(push).not.toHaveBeenCalled();
  // A shift-click on a selected endpoint deselects the range.
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 20" }), { shiftKey: true });
  expect(screen.getByRole("checkbox", { name: "Select Trace 10" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Select Trace 20" })).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Select Trace 3" })).toBeChecked();
});

it("selects only the filtered rows and excludes read-only shared traces", async () => {
  const change = vi.fn();
  const rows = traces.map((trace, i) => ({ ...trace, can_score: i !== 1, source_id: i === 2 ? "other" : "demo", source_name: i === 2 ? "Other" : "Demo" }));
  render(<TraceTable traces={rows} selected={new Set()} onSelectedChange={change} mode="browse" />);
  expect(screen.getByRole("checkbox", { name: "Select Trace 3" })).toBeDisabled();
  fireEvent.click(screen.getByRole("combobox", { name: "Filter by source" }));
  fireEvent.click(await screen.findByRole("option", { name: "Demo" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select all shown traces" }));
  expect(change).toHaveBeenLastCalledWith(new Set(["20"]));
});

it("keeps the range anchor attached to its trace after a background refresh", () => {
  const change = vi.fn();
  const { rerender } = render(<TraceTable traces={traces} selected={new Set()} onSelectedChange={change} mode="browse" />);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 10" }));
  const added = { ...traces[0], id: "1", title: "New", step_count: 1 };
  rerender(<TraceTable traces={[added, ...traces]} selected={new Set(["10"])} onSelectedChange={change} mode="browse" />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 20" }), { shiftKey: true });
  expect(change).toHaveBeenLastCalledWith(new Set(["10", "20"]));
});
