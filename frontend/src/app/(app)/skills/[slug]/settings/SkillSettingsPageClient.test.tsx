import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillSettingsPageClient from "./SkillSettingsPageClient";
import { ConfirmDialogProvider } from "../../../../../components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}
import {
  getPublicSkill,
  unpublishSkill,
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
  getPublicSkill: vi.fn(),
  unpublishSkill: vi.fn(),
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
      folder_id: "folder-1",
      slug: "shared-skill",
      title: "Shared Skill",
      description: "",
      owner_id: "user-1",
      owner_name: "henry",
      owner_display_name: "Henry",
      discoverable: false,
      cover_image_url: null,
      icon_url: null,
      view_count: 0,
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
      ...skill,
    },
    workspace_name: "Demo Workspace",
    folder_name: "Shared Skill",
    contents: { subfolders: [], pages: [], files: [], tables: [] },
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

  it("loads editable skill settings without member management", async () => {
    render(<SkillSettingsPageClient slug="shared-skill" />);

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Shared Skill")).toBeInTheDocument();
    // Person-to-person access is folder shares now, not skill members.
    expect(screen.queryByText("Members")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Visibility")).not.toBeInTheDocument();
    expect(screen.getByLabelText("List on Discover")).not.toBeChecked();
  });

  it("toggles the Discover listing", async () => {
    render(<SkillSettingsPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByLabelText("List on Discover"));

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", { discoverable: true }),
    );
  });

  it("saves title changes only", async () => {
    render(<SkillSettingsPageClient slug="shared-skill" />);

    fireEvent.change(await screen.findByLabelText("Title"), {
      target: { value: "Better Skill" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", {
        title: "Better Skill",
      }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
  });

  it("stops sharing via unpublish and returns to the workspace skills page", async () => {
    vi.mocked(unpublishSkill).mockResolvedValue(undefined);

    render(<SkillSettingsPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Stop sharing" }));
    const confirmDialog = await screen.findByRole("alertdialog", {
      name: 'Stop sharing "Shared Skill"?',
    });
    fireEvent.click(within(confirmDialog).getByRole("button", { name: "Stop sharing" }));

    await waitFor(() => expect(unpublishSkill).toHaveBeenCalledWith("skill-1"));
    expect(router.push).toHaveBeenCalledWith("/workspaces/workspace-1/skills");
  });
});
