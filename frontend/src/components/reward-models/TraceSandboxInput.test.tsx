import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { rmGetTrace, rmListTraces } from "@/lib/api";
import TraceSandboxInput from "./TraceSandboxInput";
vi.mock("@/lib/api", () => ({ rmGetTrace: vi.fn(), rmListTraces: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it("loads a JSON trace and previews the actual model input", async () => {
  const onChange = vi.fn();
  render(<TraceSandboxInput onChange={onChange} />);
  const file = new File(['{"steps":[{"role":"user","content":"Hello"}]}'], "trace.json", { type: "application/json" });
  Object.defineProperty(file, "text", { value: async () => '{"steps":[{"role":"user","content":"Hello"}]}' });
  await userEvent.setup().upload(screen.getByLabelText("Upload trace"), file);
  expect(onChange).toHaveBeenCalledWith({ steps: [{ role: "user", content: "Hello" }] });
  expect(screen.getByText("trace.json")).toBeVisible();
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
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Use an existing trace" }));
  await user.click(await screen.findByRole("button", { name: "My task · 2 steps" }));
  expect(rmGetTrace).toHaveBeenCalledWith("t1");
  expect(onChange).toHaveBeenCalledWith({ title: "My task", metadata: null, steps: [{ role: "user", content: "Hello" }] });
});
