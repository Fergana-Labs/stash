import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent, { PointerEventsCheckLevel } from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import { rmCreateRewardModel, rmListAllTraces } from "@/lib/api";
import TrainSheet from "./TrainSheet";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({
  rmListAllTraces: vi.fn(async () => ["First trace", "Second trace"].map((title, i) => ({
    id: String(i), title, step_count: 3, comment_count: 0,
    created_at: "2026-10-08T12:00:00Z",
  } as RmTraceSummary))),
  rmListRewardModels: vi.fn(async () => []),
  rmCreateRewardModel: vi.fn(),
}));

function Harness() {
  const [open, setOpen] = useState(true);
  return <TrainSheet open={open} onOpenChange={setOpen} onTrained={vi.fn()} />;
}

it("preserves trace selections and options after blank-space and outside clicks", async () => {
  const user = userEvent.setup({ pointerEventsCheck: PointerEventsCheckLevel.Never });
  render(<Harness />);
  const first = await screen.findByRole("checkbox", { name: "Select First trace" });
  await user.click(first);
  await user.click(screen.getByRole("button", { name: "Options" }));
  const name = screen.getByRole("textbox", { name: "Model name" });
  await user.clear(name);
  await user.type(name, "My selected traces");

  await user.click(screen.getByRole("dialog"));
  // Use a complete outside click: Radix defers dismissal until pointerup/click.
  await user.click(document.body);
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(first).not.toBeChecked();
  expect(name).toHaveValue("My selected traces");
});

it("queues the visible custom name and preserves it when queuing fails", async () => {
  const user = userEvent.setup();
  vi.mocked(rmCreateRewardModel).mockRejectedValueOnce(new Error("Worker unavailable"));
  render(<Harness />);
  await screen.findByRole("checkbox", { name: "Select First trace" });
  const name = screen.getByRole("textbox", { name: "Model name" });
  const create = screen.getByRole("button", { name: "Create new reward model" });
  expect(name).toBeVisible();
  expect(create).toBeDisabled();
  await user.type(name, "   ");
  expect(create).toBeDisabled();
  await user.type(name, "Heavi parts accuracy ");
  await user.click(create);
  expect(rmCreateRewardModel).toHaveBeenCalledWith(expect.objectContaining({
    name: "Heavi parts accuracy", trace_ids: ["0", "1"],
  }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Worker unavailable");
  expect(name).toHaveValue("   Heavi parts accuracy ");
  expect(create).toBeEnabled();
});

it.each(["Close", "Escape"])("still allows explicit dismissal with %s", async (action) => {
  const user = userEvent.setup();
  render(<Harness />);
  await screen.findByRole("checkbox", { name: "Select First trace" });
  if (action === "Close") await user.click(screen.getByRole("button", { name: "Close" }));
  else await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("trains only the chosen source and dates when selecting only shown traces", async () => {
  vi.mocked(rmListAllTraces).mockResolvedValueOnce([
    { id: "a", title: "Parts today", source_id: "heavi", source_name: "Heavi", created_at: new Date(2026, 9, 9, 12).toISOString() },
    { id: "b", title: "Parts yesterday", source_id: "heavi", source_name: "Heavi", created_at: new Date(2026, 9, 8, 12).toISOString() },
    { id: "c", title: "Old parts", source_id: "heavi", source_name: "Heavi", created_at: new Date(2026, 9, 7, 12).toISOString() },
    { id: "d", title: "Coding", source_id: "codex", source_name: "Henry’s Codex", created_at: new Date(2026, 9, 9, 12).toISOString() },
    { id: "e", title: "Shared review", source_id: "heavi", can_score: false, created_at: new Date(2026, 9, 9, 12).toISOString() },
  ] as RmTraceSummary[]);
  vi.mocked(rmCreateRewardModel).mockRejectedValueOnce(new Error("Test stops before training"));
  render(<Harness />);
  await screen.findByRole("checkbox", { name: "Select Parts today" });
  expect(screen.queryByRole("checkbox", { name: "Select Shared review" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("combobox", { name: "Filter by source" }));
  fireEvent.click(await screen.findByRole("option", { name: "Heavi" }));
  fireEvent.change(screen.getByLabelText("Imported from"), { target: { value: "2026-10-08" } });
  fireEvent.change(screen.getByLabelText("Imported through"), { target: { value: "2026-10-09" } });
  expect(screen.getByText(/2 selected outside these filters/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Select only shown" }));
  expect(screen.queryByText(/selected outside these filters/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Model name" }), { target: { value: "Heavi recent runs" } });
  fireEvent.click(screen.getByRole("button", { name: "Create new reward model" }));
  await waitFor(() => expect(rmCreateRewardModel).toHaveBeenLastCalledWith(expect.objectContaining({ name: "Heavi recent runs", trace_ids: ["a", "b"] })));
  expect(await screen.findByRole("alert")).toHaveTextContent("Test stops before training");
});
