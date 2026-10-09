import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent, { PointerEventsCheckLevel } from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { RmTraceSummary } from "@/lib/types";
import { rmCreateRewardModel } from "@/lib/api";
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
