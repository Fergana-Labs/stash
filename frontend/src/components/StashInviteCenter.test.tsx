import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashInviteCenter from "./StashInviteCenter";
import {
  acceptStashInvite,
  dismissStashInvite,
  listMyWorkspaces,
  listStashInvites,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
}));

vi.mock("../lib/api", () => ({
  acceptStashInvite: vi.fn(),
  dismissStashInvite: vi.fn(),
  listMyWorkspaces: vi.fn(),
  listStashInvites: vi.fn(),
}));

const invite = {
  id: "invite-1",
  stash_id: "stash-1",
  stash_slug: "partner-stash",
  stash_title: "Partner Stash",
  stash_description: "Shared launch context",
  source_workspace_id: "source-workspace",
  source_workspace_name: "Source Workspace",
  invited_by_user_id: "user-1",
  invited_by_name: "henry",
  invited_by_display_name: "Henry",
  permission: "read" as const,
  created_at: "2026-05-17T12:00:00Z",
};

const targetWorkspace = {
  id: "workspace-2",
  name: "Recipient Workspace",
  description: "",
  creator_id: "user-2",
  invite_code: "invite",
  member_count: 1,
  created_at: "2026-05-17T12:00:00Z",
  updated_at: "2026-05-17T12:00:00Z",
};

describe("StashInviteCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listStashInvites).mockResolvedValue([invite]);
    vi.mocked(listMyWorkspaces).mockResolvedValue({ workspaces: [targetWorkspace] });
    vi.mocked(acceptStashInvite).mockResolvedValue({
      id: "forked-stash",
      workspace_id: "workspace-2",
      slug: "partner-stash-fork",
      title: "Partner Stash",
      description: "",
      owner_id: "user-2",
      access: "workspace",
      discoverable: false,
      cover_image_url: null,
      view_count: 0,
      items: [],
      is_external: true,
      added_to_workspace_id: "workspace-2",
      forked_from_stash_id: "stash-1",
      created_at: "2026-05-17T12:00:00Z",
      updated_at: "2026-05-17T12:00:00Z",
    });
    vi.mocked(dismissStashInvite).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("accepts a pending invite into the selected workspace", async () => {
    render(<StashInviteCenter activeWorkspaceId="workspace-2" />);

    fireEvent.click(await screen.findByRole("button", { name: "Stash invites (1)" }));

    await screen.findByText("Partner Stash");
    fireEvent.click(screen.getByRole("button", { name: "Add Stash" }));

    await waitFor(() =>
      expect(acceptStashInvite).toHaveBeenCalledWith("invite-1", "workspace-2")
    );
    expect(nav.push).toHaveBeenCalledWith("/stashes/partner-stash-fork");
  });
});
