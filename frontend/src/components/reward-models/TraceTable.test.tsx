import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import TraceTable from "./TraceTable";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
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

it("identifies the model behind a displayed score without requiring hover", () => {
  const trace = { ...traces[0], latest_score: { reward_model_id: "model-1", reward_model_name: "Refund quality", score: 6.011 } };
  render(<TraceTable traces={[trace]} selected={new Set()} onSelectedChange={vi.fn()} mode="browse" />);
  expect(screen.getByRole("cell", { name: "6.011 Refund quality" })).toBeVisible();
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
