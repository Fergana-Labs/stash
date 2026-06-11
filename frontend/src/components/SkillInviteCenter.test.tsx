import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillInviteCenter from "./SkillInviteCenter";
import {
  dismissSkillInvite,
  listSkillInvites,
} from "../lib/api";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
}));

vi.mock("../lib/api", () => ({
  dismissSkillInvite: vi.fn(),
  listSkillInvites: vi.fn(),
}));

const invite = {
  id: "invite-1",
  skill_id: "skill-1",
  skill_slug: "partner-skill",
  skill_title: "Partner Skill",
  skill_description: "Shared launch context",
  source_workspace_id: "source-workspace",
  source_workspace_name: "Source Workspace",
  invited_by_user_id: "user-1",
  invited_by_name: "henry",
  invited_by_display_name: "Henry",
  permission: "read" as const,
  created_at: "2026-05-17T12:00:00Z",
};

describe("SkillInviteCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSkillInvites).mockResolvedValue([invite]);
    vi.mocked(dismissSkillInvite).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("opens a shared Skill for review", async () => {
    render(<SkillInviteCenter />);

    fireEvent.click(await screen.findByRole("button", { name: "Skill access (1)" }));

    await screen.findByText("Partner Skill");
    expect(
      screen.getByText("Henry has given you view access to their skill.")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View Skill" }));

    expect(nav.push).toHaveBeenCalledWith("/skills/partner-skill");
  });

  it("dismisses an access notification", async () => {
    render(<SkillInviteCenter />);

    fireEvent.click(await screen.findByRole("button", { name: "Skill access (1)" }));
    await screen.findByText("Partner Skill");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(dismissSkillInvite).toHaveBeenCalledWith("invite-1"));
    expect(screen.queryByText("Partner Skill")).not.toBeInTheDocument();
  });
});
