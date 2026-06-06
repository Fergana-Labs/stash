import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CartridgeShareModal from "./CartridgeShareModal";
import { ShareModalProvider, useShareModal } from "../../lib/shareModalContext";
import { createCartridge, getWorkspaceSidebar } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  createCartridge: vi.fn(),
  getWorkspaceSidebar: vi.fn(),
  publishCartridge: vi.fn(),
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

describe("CartridgeShareModal session sharing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getWorkspaceSidebar).mockResolvedValue({
      sessions: [
        {
          id: "session-row-uuid",
          session_id: "session-route-id",
          title: "Debug auth flow",
          linear_tickets: [],
          user_name: "Henry",
          agent_name: "Henry's Codex",
          size_bytes: 1024,
          last_at: "2026-05-14T12:00:00Z",
          updated_at: "2026-05-14T12:00:00Z",
        },
      ],
      files: { folders: [], pages: [], files: [] },
      cartridges: [],
    });
    vi.mocked(createCartridge).mockResolvedValue({
      id: "stash-1",
      workspace_id: "workspace-1",
      slug: "debug-auth-flow",
      title: "Debug auth flow",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      access: "private",
      workspace_permission: "read",
      public_permission: "none",
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      view_count: 0,
      share_count: 0,
      items: [],
      is_external: false,
      added_to_workspace_id: null,
      forked_from_cartridge_id: null,
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
        <CartridgeShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Share session" }));

    await screen.findByRole("heading", { name: "Share session as Stash" });
    expect(screen.queryByRole("button", { name: "Manage" })).not.toBeInTheDocument();
    await screen.findByText("1 item selected");
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Debug auth flow")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: "Create Stash" }));

    await waitFor(() =>
      expect(createCartridge).toHaveBeenCalledWith(
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
        { workspace_permission: "read", public_permission: "none" }
      )
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "Share session as Stash" })
      ).not.toBeInTheDocument()
    );
  });

  it("can create a private Stash", async () => {
    render(
      <ShareModalProvider>
        <OpenSessionShareButton />
        <CartridgeShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Share session" }));

    await screen.findByRole("heading", { name: "Share session as Stash" });
    await screen.findByText("1 item selected");
    fireEvent.click(screen.getByLabelText("Visibility"));
    fireEvent.click(screen.getByRole("option", { name: /Private/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create Stash" }));

    await waitFor(() =>
      expect(createCartridge).toHaveBeenCalledWith(
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
        { workspace_permission: "read", public_permission: "none" }
      )
    );
  });

  it("closes the share modal with Escape", async () => {
    render(
      <ShareModalProvider>
        <OpenSessionShareButton />
        <CartridgeShareModal />
      </ShareModalProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "Share session" }));

    await screen.findByRole("heading", { name: "Share session as Stash" });

    fireEvent.keyDown(document, { key: "Escape" });

    expect(
      screen.queryByRole("heading", { name: "Share session as Stash" })
    ).not.toBeInTheDocument();
  });
});
