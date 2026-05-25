import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StashInviteCenter from "./StashInviteCenter";
import {
  dismissStashInvite,
  listStashInvites,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
}));

vi.mock("../lib/api", () => ({
  dismissStashInvite: vi.fn(),
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
  permission: "view" as const,
  created_at: "2026-05-17T12:00:00Z",
};

describe("StashInviteCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listStashInvites).mockResolvedValue([invite]);
    vi.mocked(dismissStashInvite).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("opens a shared Stash for review", async () => {
    render(<StashInviteCenter />);

    fireEvent.click(await screen.findByRole("button", { name: "Stash access (1)" }));

    await screen.findByText("Partner Stash");
    expect(
      screen.getByText("Henry has given you view access to their Stash.")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View Stash" }));

    expect(nav.push).toHaveBeenCalledWith("/stashes/partner-stash");
  });

  it("dismisses an access notification", async () => {
    render(<StashInviteCenter />);

    fireEvent.click(await screen.findByRole("button", { name: "Stash access (1)" }));
    await screen.findByText("Partner Stash");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(dismissStashInvite).toHaveBeenCalledWith("invite-1"));
    expect(screen.queryByText("Partner Stash")).not.toBeInTheDocument();
  });
});
