import { render, screen, waitFor } from "@testing-library/react";
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
  await waitFor(() => expect(rmGetTrace).toHaveBeenCalledWith("t1"));
  await waitFor(() => expect(onChange).toHaveBeenCalled());
  const input = onChange.mock.calls[0][0];
  expect(input.title).toBe("My task");
  expect(input.steps[0].content).toBe("Hello");
  expect(input).not.toHaveProperty("annotations");
  expect(input).not.toHaveProperty("metadata");
  expect(screen.getByRole("combobox", { name: "Choose trace" })).toHaveValue("t1");
  expect(screen.getByText("Hello")).toBeVisible();
});

it("keeps uploading in the trace options menu", async () => {
  render(<TraceSandboxInput onChange={vi.fn()} />);
  expect(screen.queryByRole("button", { name: /Upload/ })).not.toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "Trace options" }));
  expect(await screen.findByRole("menuitem", { name: "Upload your own trace" })).toBeVisible();
});
