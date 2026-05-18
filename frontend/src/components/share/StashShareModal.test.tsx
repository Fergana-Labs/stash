import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashShareModal from "./StashShareModal";
import { ShareModalProvider, useShareModal } from "../../lib/shareModalContext";
import {
  addStashMember,
  createStash,
  getWorkspaceSidebar,
  listStashMembers,
  listStashes,
  searchUsers,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  addStashMember: vi.fn(),
  createStash: vi.fn(),
  deleteStash: vi.fn(),
  getWorkspaceSidebar: vi.fn(),
  listStashMembers: vi.fn(),
  listStashes: vi.fn(),
  publishStash: vi.fn(),
  removeExternalStash: vi.fn(),
  removeStashMember: vi.fn(),
  searchUsers: vi.fn(),
}));

function OpenSessionShareButton() {
  const shareModal = useShareModal();
  return (
    <button
      onClick={() =>
        shareModal.open({
          workspaceId: "workspace-1",
          workspaceName: "Demo Workspace",
          initial: [
            {
              object_type: "session",
              object_id: "session-route-id",
              label_override: "#session-route-id",
            },
          ],
        })
      }
    >
      Share session
    </button>
  );
}

function OpenManageButton() {
  const shareModal = useShareModal();
  return (
    <button
      onClick={() =>
        shareModal.open({
          workspaceId: "workspace-1",
          workspaceName: "Demo Workspace",
          tab: "manage",
        })
      }
    >
      Manage stashes
    </button>
  );
}

describe("StashShareModal session sharing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getWorkspaceSidebar).mockResolvedValue({
      sessions: [
        {
          id: "session-row-uuid",
          session_id: "session-route-id",
          title: "Debug auth flow",
          agent_name: "Henry's Codex",
          size_bytes: 1024,
          last_at: "2026-05-14T12:00:00Z",
          updated_at: "2026-05-14T12:00:00Z",
        },
      ],
      files: { folders: [], pages: [], files: [] },
      stashes: [],
    });
    vi.mocked(listStashes).mockResolvedValue([]);
    vi.mocked(listStashMembers).mockResolvedValue([]);
    vi.mocked(searchUsers).mockResolvedValue([]);
    vi.mocked(createStash).mockResolvedValue({
      id: "stash-1",
      workspace_id: "workspace-1",
      slug: "debug-auth-flow",
      title: "Debug auth flow",
      description: "",
      owner_id: "user-1",
      access: "workspace",
      discoverable: false,
      view_count: 0,
      items: [],
      is_external: false,
      added_to_workspace_id: null,
      forked_from_stash_id: null,
      created_at: "2026-05-14T12:00:00Z",
      updated_at: "2026-05-14T12:00:00Z",
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("resolves a route session id to the session row uuid before creating a Stash", async () => {
    render(
      <ShareModalProvider>
        <OpenSessionShareButton />
        <StashShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Share session" }));

    await screen.findByRole("heading", { name: "Share session as Stash" });
    await screen.findByText("1 item selected");
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Debug auth flow")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: "Create Stash" }));

    await waitFor(() =>
      expect(createStash).toHaveBeenCalledWith(
        "workspace-1",
        "Debug auth flow",
        [
          {
            object_type: "session",
            object_id: "session-row-uuid",
            position: 0,
            label_override: "Debug auth flow",
          },
        ],
        { access: "workspace" }
      )
    );
  });

  it("closes the share modal with Escape", async () => {
    render(
      <ShareModalProvider>
        <OpenSessionShareButton />
        <StashShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Share session" }));

    await screen.findByRole("heading", { name: "Share session as Stash" });

    fireEvent.keyDown(document, { key: "Escape" });

    expect(
      screen.queryByRole("heading", { name: "Share session as Stash" })
    ).not.toBeInTheDocument();
  });

  it("invites a searched user to a Stash from the Manage tab", async () => {
    vi.mocked(listStashes).mockResolvedValue([
      {
        id: "stash-1",
        workspace_id: "workspace-1",
        slug: "private-plan",
        title: "Private plan",
        description: "",
        owner_id: "user-1",
        access: "private",
        discoverable: false,
        cover_image_url: null,
        view_count: 0,
        items: [],
        is_external: false,
        added_to_workspace_id: null,
        forked_from_stash_id: null,
        created_at: "2026-05-14T12:00:00Z",
        updated_at: "2026-05-14T12:00:00Z",
      },
    ]);
    vi.mocked(searchUsers).mockResolvedValue([
      { id: "user-2", name: "ada", display_name: "Ada Lovelace" },
    ]);
    vi.mocked(addStashMember).mockResolvedValue({
      user_id: "user-2",
      name: "ada",
      display_name: "Ada Lovelace",
      permission: "write",
      granted_by: "user-1",
      created_at: "2026-05-14T12:00:00Z",
    });

    render(
      <ShareModalProvider>
        <OpenManageButton />
        <StashShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Manage stashes" }));

    await screen.findByText("Private plan");
    fireEvent.click(screen.getByRole("button", { name: /People/ }));
    fireEvent.change(screen.getByLabelText("Permission for Private plan"), {
      target: { value: "write" },
    });
    fireEvent.change(screen.getByPlaceholderText("Search people by username"), {
      target: { value: "ada" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await screen.findByText("Ada Lovelace");
    fireEvent.click(screen.getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(addStashMember).toHaveBeenCalledWith("stash-1", "user-2", "write")
    );
    await screen.findByText("@ada · can edit");
  });
});
