import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import { imPredict } from "@/lib/intuition-api";
import PlaygroundTab from "./PlaygroundTab";
const { state } = vi.hoisted(() => ({ state: { trained: true } }));
vi.mock("@/lib/api", () => ({ rmListTraces: vi.fn(async () => ({ traces: [], total: 0 })), rmGetTrace: vi.fn() }));
vi.mock("@/lib/intuition-api", () => ({ imPredict: vi.fn(), imCompare: vi.fn() }));
vi.mock("./im-ui", async (importOriginal) => {
  const original = await importOriginal<typeof import("./im-ui")>();
  const version = { number: 2, head: {}, head_stale: false, rubric: [], labels: [{ id: "send", description: "Ready" }] };
  return { ...original, useIntuition: () => ({ id: "demo", detail: { model: { output_type: "choice" }, active: state.trained ? version : null, draft: state.trained ? null : { ...version, head: null } } }) };
});

it("runs a selected trace and shows its output without legacy example review controls", async () => {
  state.trained = true;
  vi.mocked(rmListTraces).mockResolvedValue({ traces: [{ id: "trace", title: "My trace", step_count: 1, source_format: "json" }] as never, total: 1 });
  vi.mocked(rmGetTrace).mockResolvedValue({ title: "My trace", steps: [{ id: "step", index: 0, role: "user", content: "Please help" }] } as never);
  vi.mocked(imPredict).mockResolvedValue({ prediction_id: "prediction", label: "send", confidence: 0.9, probabilities: { send: 0.9 }, version: 2, rubric: {}, contributions: { send: {} } });
  render(<PlaygroundTab />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose My trace" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(await screen.findByText("confident")).toBeVisible();
  expect(imPredict).toHaveBeenCalledWith("demo", { title: "My trace", steps: [{ id: "step", index: 0, role: "user", content: "Please help", tool_name: undefined, tool_input: undefined, tool_call_id: undefined }] }, "active");
  expect(screen.queryByText("Is this right?")).not.toBeInTheDocument();
  expect(screen.queryByText(/Saved as an example/)).not.toBeInTheDocument();
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
it("requires an input before running and keeps API instructions secondary", () => {
  render(<PlaygroundTab />);
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Trace options" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Input" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Output" })).toBeVisible();
  expect(screen.getByText("Connect").closest("details")).not.toHaveAttribute("open");
  expect(screen.queryByText(/why the head decided/)).not.toBeInTheDocument();
  expect(screen.queryByText("Manual input")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load example" })).not.toBeInTheDocument();
});

it("shows the trace sandbox even when the model has no trained version", () => {
  state.trained = false;
  render(<PlaygroundTab />);
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  expect(screen.queryByText(/no trained version yet/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Write a rubric" })).not.toBeInTheDocument();
});
