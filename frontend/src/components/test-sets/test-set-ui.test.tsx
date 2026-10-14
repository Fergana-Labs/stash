import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AddToTestSetDialog } from "./test-set-ui";
import type { RmStep } from "@/lib/types";

const api = vi.hoisted(() => ({ list: vi.fn(), fromTrace: vi.fn(), create: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/test-sets-api", async (importOriginal) => ({ ...(await importOriginal<object>()), tsList: api.list, tsCaseFromTrace: api.fromTrace, tsCreate: api.create }));

const step = (index: number, role: RmStep["role"], content: string, tool_name: string | null = null): RmStep =>
  ({ id: `s${index}`, index, role, content, tool_name, tool_input: null, tool_call_id: null, metadata: null });

beforeEach(() => {
  vi.clearAllMocks();
  api.list.mockResolvedValue({ test_sets: [{ id: "set1", name: "Support regressions" }] });
  api.fromTrace.mockResolvedValue({ id: "c1" });
});

it("prefills the agent's answer after the first user turn and sends that turn", async () => {
  const onOpenChange = vi.fn();
  render(<AddToTestSetDialog open onOpenChange={onOpenChange} traceId="t1" steps={[
    step(0, "system", "You are helpful"), step(1, "user", "My blender broke"), step(2, "assistant", "", "lookup_order"),
    step(3, "assistant", "Refund issued."), step(4, "user", "Thanks"), step(5, "assistant", "Anytime"),
  ]} />);
  const expected = await screen.findByLabelText("What should the agent answer?");
  expect(expected).toHaveValue("Refund issued.");
  fireEvent.change(expected, { target: { value: "A refund for order 5530." } });
  fireEvent.click(screen.getByRole("button", { name: "Add case" }));
  await waitFor(() => expect(api.fromTrace).toHaveBeenCalledWith("set1", { trace_id: "t1", upto_idx: 1, expected: "A refund for order 5530." }));
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

it("uses a behavior hit's end step and starts the expected answer empty", async () => {
  render(<AddToTestSetDialog open onOpenChange={() => {}} traceId="t2" uptoIdx={7} />);
  const expected = await screen.findByPlaceholderText("What it should have said");
  expect(expected).toHaveValue("");
  expect(screen.queryByText("Start from")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add case" }));
  await waitFor(() => expect(api.fromTrace).toHaveBeenCalledWith("set1", { trace_id: "t2", upto_idx: 7, expected: "" }));
});
