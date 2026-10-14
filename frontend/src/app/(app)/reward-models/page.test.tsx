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
const behaviorsApi = vi.hoisted(() => ({ overview: vi.fn(), search: vi.fn(), releases: vi.fn() }));
vi.mock("@/lib/behaviors-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/behaviors-api")>()),
  getBehaviorOverview: behaviorsApi.overview, searchBehaviorTraces: behaviorsApi.search, listReleases: behaviorsApi.releases,
}));
const frustration = {
  behavior: { id: "b1", name: "User frustration", actor: "user", severity: "high", enabled: true, definition: "The user is annoyed.", detector: "llm" },
  series: [{ day: "2026-10-09", hits: 2, traces_with_hit: 2, traces_scanned: 3, rate: 0.6 }], last_7_days: 2, previous_7_days: 0, change: null, traces_scanned: 3,
};
const rows = [1, 2, 3].map((n) => ({ id: String(n), title: `Trace ${n}`, step_count: n, comment_count: 0, source_format: "otel", created_at: "2026-10-09T00:00:00Z" }) as RmTraceSummary);
beforeEach(() => {
  vi.resetAllMocks(); list.mockResolvedValue(rows); confirm.mockResolvedValue(true); remove.mockResolvedValue(undefined);
  behaviorsApi.overview.mockResolvedValue({ days: 30, behaviors: [frustration] });
  behaviorsApi.search.mockResolvedValue({ query: "", mode: "browse", results: [] });
  behaviorsApi.releases.mockResolvedValue({ releases: [] });
});
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

it("filters the trace table to a monitor's behavior and back", async () => {
  render(<TracesPage />);
  await screen.findByRole("checkbox", { name: "Select Trace 1" });
  behaviorsApi.search.mockResolvedValue({ query: "", mode: "browse", results: [{
    trace_id: "2", title: "Trace 2", created_at: "2026-10-09T00:00:00Z", agent: null, input: null, output: null, score: null, segments: [],
    behaviors: [{ id: "h1", behavior_id: "b1", name: "User frustration", actor: "user", start_idx: 1, end_idx: 1, review: null, confidence: null }],
  }] });
  fireEvent.click(await screen.findByRole("button", { name: /User frustration/ }));
  await waitFor(() => expect(behaviorsApi.search).toHaveBeenLastCalledWith(expect.objectContaining({ behaviors: ["b1"] })));
  expect(await screen.findByRole("region", { name: "User frustration over time" })).toBeVisible();
  expect(screen.getByRole("link", { name: /Open/ })).toHaveAttribute("href", "/reward-models/behaviors/b1");
  await waitFor(() => expect(screen.queryByRole("checkbox", { name: "Select Trace 1" })).not.toBeInTheDocument());
  expect(screen.getByRole("checkbox", { name: "Select Trace 2" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /User frustration/, pressed: true }));
  expect(await screen.findByRole("checkbox", { name: "Select Trace 1" })).toBeVisible();
  expect(screen.queryByRole("region", { name: "User frustration over time" })).not.toBeInTheDocument();
});
