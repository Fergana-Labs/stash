import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillSettingsPageClient from "./SkillSettingsPageClient";
import {
  getPublicSkill,
  updateSkill,
  type PublicSkillDetail,
} from "../../../../../lib/api";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  user: {
    id: "user-1",
    name: "henry",
    display_name: "Henry",
    description: "",
    created_at: "2026-05-11T00:00:00Z",
    last_seen: "2026-05-11T00:00:00Z",
  },
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("../../../../../components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("../../../../../components/ShellChromeContext", () => ({
  useActiveWorkspaceId: vi.fn(),
}));

vi.mock("../../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: authState.user,
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../../../lib/skillNavigationCache", () => ({
  resetSkillNavigationCache: vi.fn(),
}));

vi.mock("../../../../../lib/api", () => ({
  deleteSkill: vi.fn(),
  getPublicSkill: vi.fn(),
  updateSkill: vi.fn(),
  uploadFile: vi.fn(),
}));

function skillDetail(
  skill: Partial<PublicSkillDetail["skill"]> = {},
): PublicSkillDetail {
  return {
    skill: {
      id: "skill-1",
      workspace_id: "workspace-1",
      slug: "shared-skill",
      title: "Shared Skill",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      access: "public",
      workspace_permission: "read",
      public_permission: "read",
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      view_count: 0,
      share_count: 0,
      items: [],
      is_external: false,
      added_to_workspace_id: null,
      forked_from_skill_id: null,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
      ...skill,
    },
    workspace_name: "Demo Workspace",
    items: [],
    can_write: true,
  };
}

describe("SkillSettingsPageClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPublicSkill).mockResolvedValue(skillDetail());
    vi.mocked(updateSkill).mockImplementation(async (_skillId, updates) => ({
      ...skillDetail().skill,
      ...updates,
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("loads editable skill settings", async () => {
    render(<SkillSettingsPageClient slug="shared-skill" />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Shared Skill")).toBeInTheDocument();
    expect(screen.queryByText("Members")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Visibility")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Workspace access")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Public access")).not.toBeInTheDocument();
    expect(screen.queryByText("List on Discover")).not.toBeInTheDocument();
  });

  it("saves title changes only", async () => {
    render(<SkillSettingsPageClient slug="shared-skill" />);

    const titleInput = await screen.findByLabelText("Title");
    fireEvent.change(titleInput, {
      target: { value: "Better Skill" },
    });
    await waitFor(() => expect(titleInput).toHaveValue("Better Skill"));

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", {
        title: "Better Skill",
      }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });
});
