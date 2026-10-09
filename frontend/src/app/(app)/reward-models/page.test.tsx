import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import TracesPage from "./page";

const { list, remove, confirm, push, success, error } = vi.hoisted(() => ({ list: vi.fn(), remove: vi.fn(), confirm: vi.fn(), push: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/components/ConfirmDialog", () => ({ useConfirm: () => confirm }));
vi.mock("sonner", () => ({ toast: { success, error } }));
vi.mock("@/lib/api", () => ({ rmListAllTraces: list, rmDeleteTrace: remove }));
vi.mock("@/components/reward-models/ImportTracesDialog", () => ({ default: () => null }));
vi.mock("@/components/reward-models/ConnectAgentDialog", () => ({ default: () => null }));
vi.mock("@/components/reward-models/TrainPanel", () => ({ default: () => null }));
vi.mock("@/components/reward-models/TraceDropzone", () => ({ default: ({ children }: { children: ReactNode }) => children }));
const rows = [1, 2, 3].map((n) => ({ id: String(n), title: `Trace ${n}`, step_count: n, comment_count: 0, source_format: "otel", created_at: "2026-10-09T00:00:00Z" }) as RmTraceSummary);
beforeEach(() => { vi.resetAllMocks(); list.mockResolvedValue(rows); confirm.mockResolvedValue(true); remove.mockResolvedValue(undefined); });
async function select() {
  fireEvent.click(await screen.findByRole("checkbox", { name: "Select Trace 1" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Trace 3" }), { shiftKey: true });
  expect(screen.getByText("3 traces selected")).toBeVisible();
}
it("confirms and deletes a selected range together", async () => {
  render(<TracesPage />);
  await select();
  list.mockResolvedValue([]);
  fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
  await waitFor(() => expect(remove).toHaveBeenCalledTimes(3));
  expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ title: "Delete 3 traces?", confirmLabel: "Delete 3 traces" }));
  expect(remove.mock.calls.map(([id]) => id)).toEqual(["1", "2", "3"]);
  await waitFor(() => expect(screen.queryByText("3 traces selected")).not.toBeInTheDocument());
});
it("keeps the selection when confirmation is cancelled", async () => {
  confirm.mockResolvedValue(false);
  render(<TracesPage />);
  await select();
  fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(remove).not.toHaveBeenCalled();
  expect(screen.getByText("3 traces selected")).toBeVisible();
});
it("retains failed deletions for retry and reports partial success", async () => {
  remove.mockImplementation(async (id) => { if (id === "2") throw new Error("Unavailable"); });
  render(<TracesPage />);
  await select();
  list.mockResolvedValue([rows[1]]);
  fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
  expect(await screen.findByText("1 trace selected")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "Select Trace 2" })).toBeChecked();
  expect(success).toHaveBeenCalledWith("Deleted 2 traces");
  expect(error).toHaveBeenCalledWith(expect.stringContaining("Couldn’t delete 1 trace"));
});
