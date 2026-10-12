import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import PlaygroundTab from "./PlaygroundTab";
const { state } = vi.hoisted(() => ({ state: { trained: true } }));
vi.mock("@/lib/api", () => ({ rmListTraces: vi.fn(async () => ({ traces: [], total: 0 })), rmGetTrace: vi.fn() }));
vi.mock("./im-ui", async (importOriginal) => {
  const original = await importOriginal<typeof import("./im-ui")>();
  const version = { number: 2, head: {}, head_stale: false, rubric: [], labels: [{ id: "send", description: "Ready" }] };
  return { ...original, useIntuition: () => ({ id: "demo", detail: { model: { output_type: "choice" }, active: state.trained ? version : null, draft: state.trained ? null : { ...version, head: null } }, examples: [], goTo: vi.fn(), reload: vi.fn(), reloadExamples: vi.fn() }) };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
it("requires an input before running and keeps API instructions secondary", () => {
  render(<PlaygroundTab />);
  expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Trace options" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Input" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Output" })).toBeVisible();
  expect(screen.getByText("API access").closest("details")).not.toHaveAttribute("open");
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
