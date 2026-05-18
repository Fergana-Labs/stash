import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashShareDialog from "./StashShareDialog";
import {
  getStashShare,
  searchUsers,
  updateStashShare,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  getStashShare: vi.fn(),
  searchUsers: vi.fn(),
  updateStash: vi.fn(),
  updateStashShare: vi.fn(),
}));

const stash = {
  id: "stash-1",
  workspace_id: "workspace-1",
  slug: "shared-stash",
  title: "Shared Stash",
  description: "",
  owner_id: "user-1",
  access: "private" as const,
  discoverable: false,
  cover_image_url: null,
  icon_url: null,
  view_count: 0,
  items: [],
  is_external: false,
  added_to_workspace_id: null,
  forked_from_stash_id: null,
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
};

const share = {
  stash,
  url: "https://app.joinstash.ai/stashes/shared-stash",
  owner: {
    user_id: "user-1",
    name: "owner",
    display_name: "Owner",
  },
  members: [],
};

describe("StashShareDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getStashShare).mockResolvedValue(share);
    vi.mocked(searchUsers).mockResolvedValue([
      {
        id: "user-2",
        name: "sam",
        display_name: "Sam account",
      },
    ]);
    vi.mocked(updateStashShare).mockResolvedValue({
      ...share,
      members: [
        {
          user_id: "user-2",
          name: "sam",
          display_name: "Sam account",
          permission: "read",
          granted_by: "user-1",
          created_at: "2026-05-11T00:00:00Z",
        },
      ],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("labels Stash-level sharing and grants a selected user access", async () => {
    const onChanged = vi.fn().mockResolvedValue(undefined);

    render(
      <StashShareDialog
        stash={stash}
        workspaceName="Demo Workspace"
        canWrite
        canManageAccess
        open
        onClose={vi.fn()}
        onChanged={onChanged}
      />
    );

    await screen.findByText("Stash-level");
    expect(
      screen.getByText("People added here can access this Stash without joining Demo Workspace.")
    ).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Add people by username"), {
      target: { value: "sam" },
    });
    fireEvent.click(await screen.findByText("@sam"));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(updateStashShare).toHaveBeenCalledWith("stash-1", {
        people: [{ user_id: "user-2", permission: "read" }],
      })
    );
    expect(await screen.findByText("Sam account")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
