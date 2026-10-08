import { useState } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import TraceTable from "./TraceTable";

const { push, search } = vi.hoisted(() => ({ push: vi.fn(), search: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmListAllTraces: search }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
beforeEach(() => vi.clearAllMocks());

const traces: RmTraceSummary[] = [20, 3, 10].map((steps) => ({
  id: String(steps), title: `Trace ${steps}`, step_count: steps,
  external_id: null, source_format: "otel", positive_count: 0, negative_count: 0,
  comment_count: 0, label_error_count: 0, latest_score: null, created_at: "2026-09-29T00:00:00Z",
}));

function Table() {
  const [selected, setSelected] = useState(new Set(["20"]));
  return <TraceTable traces={traces} selected={selected} onSelectedChange={setSelected} mode="browse" />;
}

it("clicking a column toggles its sort direction without changing selected traces", () => {
  render(<Table />);
  const order = () => screen.getAllByRole("row").slice(1).map((row) => within(row).getByRole("link").textContent);
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  expect(order()).toEqual(["Trace 3", "Trace 10", "Trace 20"]);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  expect(order()).toEqual(["Trace 20", "Trace 10", "Trace 3"]);
  expect(screen.getByRole("columnheader", { name: "Steps" })).toHaveAttribute("aria-sort", "descending");
  expect(screen.getByRole("checkbox", { name: "Select Trace 20" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Select Trace 3" })).not.toBeChecked();
});

it("opens a trace from its non-title cells", () => {
  render(<Table />);
  fireEvent.click(screen.getByRole("cell", { name: "20" }));
  expect(push).toHaveBeenCalledWith("/reward-models/traces/20");
});

it("keeps selection and deletion separate from opening the trace", () => {
  const onDelete = vi.fn();
  const onSelectedChange = vi.fn();
  render(<TraceTable traces={[traces[0]]} selected={new Set()} onSelectedChange={onSelectedChange} mode="browse" onDelete={onDelete} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 20" }));
  expect(onSelectedChange).toHaveBeenCalledWith(new Set(["20"]));
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
  render(<Table />);
  const input = screen.getByRole("textbox", { name: "Search titles and trace content" });
  fireEvent.change(input, { target: { value: "old" } });
  await waitFor(() => expect(search).toHaveBeenCalledWith("old"));
  fireEvent.change(input, { target: { value: "needle in tool output" } });
  await waitFor(() => expect(screen.getByRole("link", { name: "Trace 3" })).toBeVisible());
  await act(async () => finishOld([traces[0]]));
  expect(screen.queryByRole("link", { name: "Trace 20" })).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "" } });
  expect(screen.getByRole("link", { name: "Trace 20" })).toBeVisible();
});
