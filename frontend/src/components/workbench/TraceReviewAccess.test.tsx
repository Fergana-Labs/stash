import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import TraceReviewAccess from "./TraceReviewAccess";

const api = vi.hoisted(() => ({ list: vi.fn(), suggest: vi.fn(), add: vi.fn(), remove: vi.fn() }));
vi.mock("@/lib/workbench-api", () => ({ wbTraceReviewers: api.list, wbReviewerSuggestions: api.suggest, wbAddReviewer: api.add, wbRemoveReviewer: api.remove }));

it("finds a teammate by name and only grants access after explicit submission", async () => {
  api.list.mockResolvedValue({ owner_user_id: "owner", reviewers: [] });
  api.suggest.mockResolvedValue([{ user_id: "sam", display_name: "Sam", email: "sam@example.test" }]);
  api.add.mockResolvedValue({});
  render(<TraceReviewAccess traceId="trace" viewerId="owner" />);
  expect(api.list).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
  fireEvent.pointerDown(screen.getByRole("button", { name: "Trace actions" }), { button: 0, pointerId: 1 });
  expect(api.list).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("menuitem", { name: "Share" }));
  const input = await screen.findByRole("combobox", { name: "Name or email" });
  fireEvent.change(input, { target: { value: "Sam" } });
  expect(await screen.findByRole("option", { name: "Sam sam@example.test" })).toBeVisible();
  expect(api.suggest).toHaveBeenCalledWith("trace", "Sam");
  fireEvent.keyDown(input, { key: "Enter" });
  expect(input).toHaveValue("sam@example.test");
  expect(api.add).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Grant access" }));
  await waitFor(() => expect(api.add).toHaveBeenCalledWith("trace", "sam@example.test"));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByRole("button", { name: "Trace actions" })).toHaveFocus();
});
