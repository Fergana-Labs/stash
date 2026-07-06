import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SessionFolderShareModal from "./SessionFolderShareModal";
import {
  listObjectShares,
  revokePendingShareInvite,
  setGeneralAccess,
  shareObjectByEmail,
  unshareObject,
} from "../../lib/api";
import type { SessionFolder } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  listObjectShares: vi.fn(),
  revokePendingShareInvite: vi.fn(),
  setGeneralAccess: vi.fn(),
  shareObjectByEmail: vi.fn(),
  unshareObject: vi.fn(),
}));

const folder: SessionFolder = {
  id: "folder-1",
  owner_user_id: "user-1",
  slug: "shared-folder",
  name: "Shared Folder",
  owner_display_name: "Henry",
  access: "private",
  is_default: false,
  view_count: 0,
  session_count: 0,
  share_count: 1,
};

describe("SessionFolderShareModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(shareObjectByEmail).mockResolvedValue();
    vi.mocked(revokePendingShareInvite).mockResolvedValue();
    vi.mocked(unshareObject).mockResolvedValue();
    vi.mocked(setGeneralAccess).mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
  });

  it("revokes pending email invites instead of treating them as user shares", async () => {
    vi.mocked(listObjectShares)
      .mockResolvedValueOnce({
        shares: [
          {
            principal_type: "user",
            principal_id: null,
            label: "pending@example.com",
            email: "pending@example.com",
            permission: "read",
            pending: true,
          },
        ],
        general_access: "restricted",
      })
      .mockResolvedValueOnce({ shares: [], general_access: "restricted" });

    render(
      <SessionFolderShareModal
        folder={folder}
        onClose={vi.fn()}
        onChanged={vi.fn()}
      />
    );

    await screen.findByText("pending@example.com");
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(revokePendingShareInvite).toHaveBeenCalledWith(
        "session_folder",
        "folder-1",
        "pending@example.com"
      )
    );
    expect(unshareObject).not.toHaveBeenCalled();
    await waitFor(() => expect(listObjectShares).toHaveBeenCalledTimes(2));
  });

  it("makes the folder public through the general-access endpoint", async () => {
    vi.mocked(listObjectShares).mockResolvedValue({
      shares: [],
      general_access: "restricted",
    });
    const onChanged = vi.fn();

    render(
      <SessionFolderShareModal
        folder={folder}
        onClose={vi.fn()}
        onChanged={onChanged}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Public" }));

    await waitFor(() =>
      expect(setGeneralAccess).toHaveBeenCalledWith(
        "session_folder",
        "folder-1",
        "public"
      )
    );
    expect(onChanged).toHaveBeenCalled();
    // The public link surfaces once the folder is public.
    expect(
      screen.getByText(`${window.location.origin}/session-folders/shared-folder`)
    ).toBeInTheDocument();
  });
});
