import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ReviewPage from "./page";

const wz = vi.hoisted(() => ({ reviewView: vi.fn(), reviewRate: vi.fn() }));
vi.mock("@/lib/wizard-api", () => wz);

it("walks an invited reviewer through the calibration items blind", async () => {
  wz.reviewView.mockResolvedValue({
    model: "Reply triage", reviewer: "Dana", instructions: "Would we send this reply?",
    label_boundaries: [{ id: "send", means: "Correct and polite", not: "Merely polite" }],
    labels: [{ id: "send", description: "Send" }, { id: "rewrite", description: "Rewrite" }],
    items: [
      { id: "e1", item: "first", item_b: null, my_label: "send", my_note: "" },
      { id: "e2", item: "second", item_b: null, my_label: null, my_note: null },
    ],
  });
  wz.reviewRate.mockResolvedValue({ rated: true });
  await act(async () => { render(<ReviewPage params={Promise.resolve({ token: "tok" })} />); });
  // Resumes at the first unlabeled item and shows the label boundary.
  expect(await screen.findByText("second")).toBeVisible();
  expect(screen.getByText("(not: Merely polite)", { exact: false })).toBeVisible();
  expect(screen.getByText("1 of 2 done")).toBeVisible();
  fireEvent.keyDown(window, { key: "2" });
  await waitFor(() => expect(wz.reviewRate).toHaveBeenCalledWith("tok", "e2", "rewrite", ""));
  expect(await screen.findByText("All done — thank you.")).toBeVisible();
});
