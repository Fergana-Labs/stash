import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { rmGetTrace } from "@/lib/api";
import type { RmTraceDetail } from "@/lib/types";
import TraceContextViewer from "./TraceContextViewer";
vi.mock("@/lib/api", () => ({ rmGetTrace: vi.fn() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("step=call") }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
beforeEach(() => vi.resetAllMocks());
it("opens at a tool call and moves the context boundary when selecting another checkpoint", async () => {
  vi.mocked(rmGetTrace).mockResolvedValue({ id: "trace", title: "Task", steps: [
    { id: "system", index: 0, role: "system", content: "Follow these rules" },
    { id: "call", index: 1, role: "assistant", content: "Searching", tool_name: "search", tool_input: { query: "filter" } },
    { id: "result", index: 2, role: "tool", content: "Search results" },
  ] } as unknown as RmTraceDetail);
  render(<TraceContextViewer traceId="trace" />);
  expect(await screen.findByText("Recorded context · 1 messages")).toBeVisible();
  const history = screen.getByText("Recorded context · 1 messages").closest("section")!;
  expect(within(history).getByText("Follow these rules")).toBeVisible();
  expect(within(history).queryByText("Searching")).not.toBeInTheDocument();
  expect(screen.queryByText("Search results")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Checkpoint" }), { target: { value: "result" } });
  expect(screen.getByText("Recorded context · 2 messages")).toBeVisible();
  expect(screen.getByText("Search results")).toBeVisible();
});
it("shows load failures and retries the same trace", async () => {
  vi.mocked(rmGetTrace).mockRejectedValueOnce(new Error("Unavailable")).mockResolvedValue({ id: "trace", title: "Task", steps: [] } as unknown as RmTraceDetail);
  render(<TraceContextViewer traceId="trace" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("This trace has no recorded steps.")).toBeVisible();
});
