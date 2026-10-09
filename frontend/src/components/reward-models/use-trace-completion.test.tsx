import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { rmEstimateCompletion } from "@/lib/api";
import type { RmStep } from "@/lib/types";
import { useTraceCompletion } from "./use-trace-completion";

vi.mock("@/lib/api", () => ({ rmEstimateCompletion: vi.fn() }));
afterEach(() => { vi.clearAllMocks(); vi.useRealTimers(); });
const steps = [{ id: "one", role: "user", content: "Fix the bug", tool_name: null, tool_input: null } as RmStep];
const ready = { tasks: [], pending: false, unavailable: false };

it("ignores an old trace's response and does not regenerate on identical polling data", async () => {
  let finish!: (value: typeof ready) => void;
  vi.mocked(rmEstimateCompletion).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  vi.mocked(rmEstimateCompletion).mockResolvedValue(ready);
  const view = renderHook(({ id, rows }) => useTraceCompletion(id, rows), { initialProps: { id: "old", rows: steps } });
  view.rerender({ id: "new", rows: steps });
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  await act(async () => finish({ ...ready, pending: true }));
  expect(view.result.current.loading).toBe(false);
  view.rerender({ id: "new", rows: steps.map((step) => ({ ...step })) });
  expect(rmEstimateCompletion).toHaveBeenCalledTimes(2);
  view.rerender({ id: "new", rows: [{ ...steps[0], content: "A changed request" }] });
  await waitFor(() => expect(rmEstimateCompletion).toHaveBeenCalledTimes(3));
});

it("retries a pending lease and recovers from a temporary network failure", async () => {
  vi.useFakeTimers();
  vi.mocked(rmEstimateCompletion).mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValueOnce({ ...ready, pending: true }).mockResolvedValue(ready);
  const view = renderHook(() => useTraceCompletion("trace", steps));
  await act(async () => {});
  expect(view.result.current.loading).toBe(false);
  await act(async () => vi.advanceTimersByTime(3000));
  expect(view.result.current.loading).toBe(true);
  await act(async () => vi.advanceTimersByTime(3000));
  expect(view.result.current.loading).toBe(false);
  expect(rmEstimateCompletion).toHaveBeenCalledTimes(3);
});
