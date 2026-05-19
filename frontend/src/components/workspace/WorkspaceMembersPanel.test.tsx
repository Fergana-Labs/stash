import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceMembersPanel from "./WorkspaceMembersPanel";
import {
  apiFetch,
  createInviteToken,
  setWorkspaceMemberRole,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  apiFetch: vi.fn(),
  createInviteToken: vi.fn(),
  kickWorkspaceMember: vi.fn(),
  setWorkspaceMemberRole: vi.fn(),
}));

const members = [
  {
    user_id: "user-1",
    name: "henry",
    display_name: "Henry",
    role: "owner",
    joined_at: "2026-05-11T00:00:00Z",
  },
  {
    user_id: "user-2",
    name: "ada",
    display_name: "Ada",
    role: "editor",
    joined_at: "2026-05-12T00:00:00Z",
  },
];

describe("WorkspaceMembersPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiFetch).mockResolvedValue({});
    vi.mocked(createInviteToken).mockResolvedValue({
      id: "invite-1",
      token: "invite-token",
      workspace_id: "workspace-1",
      expires_at: "2026-05-18T00:00:00Z",
    });
    vi.mocked(setWorkspaceMemberRole).mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("adds members and generates invite links for workspace admins", async () => {
    const onReload = vi.fn().mockResolvedValue(undefined);

    render(
      <WorkspaceMembersPanel
        workspaceId="workspace-1"
        members={members}
        currentUserId="user-1"
        canManage
        onReload={onReload}
      />
    );

    fireEvent.change(screen.getByPlaceholderText("Username"), {
      target: { value: "grace" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith("/api/v1/workspaces/workspace-1/members", {
        method: "POST",
        body: JSON.stringify({ username: "grace" }),
      })
    );
    expect(onReload).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Generate invite link" }));

    await screen.findByText(/\/join\/invite-token/);
    fireEvent.click(screen.getByText(/\/join\/invite-token/));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining("/join/invite-token")
    );
  });

  it("updates roles from the members list", async () => {
    const onReload = vi.fn().mockResolvedValue(undefined);

    render(
      <WorkspaceMembersPanel
        workspaceId="workspace-1"
        members={members}
        currentUserId="user-1"
        canManage
        onReload={onReload}
        showInviteControls={false}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Editor" }));
    fireEvent.click(screen.getByRole("option", { name: /Viewer/ }));

    await waitFor(() =>
      expect(setWorkspaceMemberRole).toHaveBeenCalledWith("workspace-1", "user-2", "viewer")
    );
    expect(onReload).toHaveBeenCalledTimes(1);
  });
});
