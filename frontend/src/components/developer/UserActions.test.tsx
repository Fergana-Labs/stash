import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialogProvider } from "@/components/ConfirmDialog";
import type { EndUser } from "@/lib/types";
import UserActions from "./UserActions";

const updateUser = vi.fn();
const deleteUser = vi.fn();

vi.mock("@/lib/api", () => ({
  updateUser: (...args: unknown[]) => updateUser(...args),
  deleteUser: (...args: unknown[]) => deleteUser(...args),
}));

const user: EndUser = {
  id: "user-1",
  workspace_id: "workspace-1",
  external_id: "org_acme",
  name: "Acme",
  share_wiki: true,
  wiki_folder_id: "folder-1",
  created_at: "2026-01-01T00:00:00Z",
  session_count: 2,
  last_session_at: null,
};

function renderActions(onChanged = vi.fn()) {
  render(
    <ConfirmDialogProvider>
      <UserActions user={user} onChanged={onChanged} />
    </ConfirmDialogProvider>,
  );
  return onChanged;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UserActions", () => {
  it("renames a user and refreshes the list", async () => {
    updateUser.mockResolvedValue({});
    const onChanged = renderActions();

    await userEvent.click(screen.getByLabelText("Actions for Acme"));
    await userEvent.click(await screen.findByText("Rename"));
    fireEvent.change(screen.getByLabelText("Name for Acme"), {
      target: { value: "  Acme Freight  " },
    });
    await userEvent.click(screen.getByLabelText("Save name"));

    await waitFor(() => expect(updateUser).toHaveBeenCalledWith("user-1", { name: "Acme Freight" }));
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("explains retention before deleting a user", async () => {
    deleteUser.mockResolvedValue(undefined);
    const onChanged = renderActions();

    await userEvent.click(screen.getByLabelText("Actions for Acme"));
    await userEvent.click(await screen.findByText("Delete"));
    expect(screen.getByText(/Historical sessions and uploaded files stay/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Delete user"));

    await waitFor(() => expect(deleteUser).toHaveBeenCalledWith("user-1"));
    expect(onChanged).toHaveBeenCalledOnce();
  });
});
