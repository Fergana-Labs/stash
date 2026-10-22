import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import TraceSandboxInput from "./TraceSandboxInput";
vi.mock("@/lib/api", () => ({ rmGetTrace: vi.fn(), rmListTraces: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); vi.mocked(rmListTraces).mockResolvedValue({ traces: [], total: 0 }); });

it("loads a JSON trace and previews the actual model input", async () => {
  const onChange = vi.fn();
  render(<TraceSandboxInput onChange={onChange} />);
  const file = new File(['{"steps":[{"role":"user","content":"Hello"}]}'], "trace.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: async () => '{"steps":[{"role":"user","content":"Hello"}]}' });
  await userEvent.setup().upload(screen.getByLabelText("Upload trace"), file);
  expect(onChange).toHaveBeenCalledWith({ steps: [{ role: "user", content: "Hello" }] });
  expect(screen.getByText("Hello")).toBeVisible();
});

it("rejects malformed JSON without replacing the model input", async () => {
  const onChange = vi.fn();
  render(<TraceSandboxInput onChange={onChange} />);
  const file = new File(['broken'], "trace.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: async () => 'broken' });
  await userEvent.setup().upload(screen.getByLabelText("Upload trace"), file);
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(onChange).not.toHaveBeenCalled();
});

it("reads the selected existing trace and omits annotations and previous scores", async () => {
  vi.mocked(rmListTraces).mockResolvedValue({ traces: [{ id: "t1", title: "My task", step_count: 2 } as never], total: 1 });
  vi.mocked(rmGetTrace).mockResolvedValue({ title: "My task", metadata: null, steps: [{ role: "user", content: "Hello" }], annotations: [{ rating: 1 }], scores: [99] } as never);
  const onChange = vi.fn();
  render(<TraceSandboxInput onChange={onChange} />);
  const choose = await screen.findByRole("button", { name: "Choose My task" });
  expect(rmGetTrace).not.toHaveBeenCalled();
  await userEvent.setup().click(choose);
  await waitFor(() => expect(rmGetTrace).toHaveBeenCalledWith("t1"));
  await waitFor(() => expect(onChange).toHaveBeenCalled());
  const input = onChange.mock.calls[0][0];
  expect(input.title).toBe("My task");
  expect(input.steps[0].content).toBe("Hello");
  expect(input).not.toHaveProperty("annotations");
  expect(input).not.toHaveProperty("metadata");
  expect(screen.getByRole("button", { name: "Change trace" })).toBeVisible();
  expect(screen.getByText("Hello")).toBeVisible();
  await userEvent.setup().click(screen.getByRole("button", { name: "Change trace" }));
  expect(screen.getByRole("table", { name: "Choose a trace" })).toBeVisible();
  expect(onChange).toHaveBeenLastCalledWith("");
});

it("keeps uploading in the trace options menu", async () => {
  render(<TraceSandboxInput onChange={vi.fn()} />);
  expect(screen.queryByRole("button", { name: /Upload/ })).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "Trace options" }));
  expect(await screen.findByRole("menuitem", { name: "Upload your own trace" })).toBeVisible();
});


it("highlights immediately and ignores an older trace response after a second click", async () => {
  const summaries = [{ id: "a", title: "First", step_count: 1 }, { id: "b", title: "Second", step_count: 1 }];
  vi.mocked(rmListTraces).mockResolvedValue({ traces: summaries as never, total: 2 });
  let first!: (value: never) => void;
  vi.mocked(rmGetTrace).mockImplementation((id) => id === "a" ? new Promise((resolve) => { first = resolve; }) : Promise.resolve({ id: "b", title: "Second", steps: [] } as never));
  const onTraceChange = vi.fn();
  render(<TraceSandboxInput selectionOnly onChange={vi.fn()} onTraceChange={onTraceChange} />);
  fireEvent.click(await screen.findByRole("button", { name: "Choose First" }));
  expect(screen.getByRole("button", { name: "Choose First" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Choose Second" }));
  expect(screen.getByRole("button", { name: "Choose Second" })).toHaveAttribute("aria-pressed", "true");
  await waitFor(() => expect(onTraceChange).toHaveBeenCalledWith(expect.objectContaining({ id: "b" })));
  await act(async () => first({ id: "a", title: "First", steps: [] } as never));
  expect(onTraceChange).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Choose Second" })).toHaveAttribute("aria-pressed", "true");
});

it("appends pages on scroll and resets them when searching", async () => {
  const page = Array.from({ length: 25 }, (_, i) => ({ id: `t${i}`, title: `Task ${i}`, step_count: 1 }));
  vi.mocked(rmListTraces).mockImplementation(async (_limit, offset, query) => query ? { traces: [{ id: "match", title: "Matching task", step_count: 1 }] as never, total: 1 } : { traces: (offset ? [{ id: "last", title: "Last task", step_count: 1 }] : page) as never, total: 26 });
  render(<TraceSandboxInput selectionOnly onChange={vi.fn()} />);
  await screen.findByRole("button", { name: "Choose Task 0" });
  fireEvent.scroll(screen.getByRole("region", { name: "Available traces" }));
  expect(await screen.findByRole("button", { name: "Choose Last task" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Choose Task 0" })).toBeVisible();
  expect(rmListTraces).toHaveBeenCalledWith(25, 25, "");
  fireEvent.change(screen.getByRole("textbox", { name: "Search existing traces" }), { target: { value: "match" } });
  expect(await screen.findByRole("button", { name: "Choose Matching task" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Choose Task 0" })).not.toBeInTheDocument();
  expect(rmListTraces).toHaveBeenLastCalledWith(25, 0, "match");
});

it("continues past pages containing traces this user cannot score", async () => {
  vi.mocked(rmListTraces).mockImplementation(async (_limit, offset) => ({ traces: (offset ? [{ id: "owned", title: "Owned task", step_count: 1, can_score: true }] : Array.from({ length: 25 }, (_, i) => ({ id: `shared${i}`, title: `Shared ${i}`, can_score: false }))) as never, total: 26 }));
  render(<TraceSandboxInput selectionOnly scoreableOnly onChange={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("0 of 26 traces, Scroll for more")).toBeVisible());
  expect(screen.queryByText(/No traces found/)).not.toBeInTheDocument();
  fireEvent.scroll(screen.getByRole("region", { name: "Available traces" }));
  expect(await screen.findByRole("button", { name: "Choose Owned task" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Choose Shared 0" })).not.toBeInTheDocument();
});
