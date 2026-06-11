import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillPageClient from "./SkillPageClient";
import {
  ShellChromeProvider,
  useShellChromeValue,
} from "../../../../components/ShellChromeContext";
import { ConfirmDialogProvider } from "../../../../components/ConfirmDialog";
import {
  addSkillMember,
  getActivityTimeline,
  getEmbeddingProjection,
  getMe,
  getPublicSkill,
  listSkillMembers,
  searchUsers,
  updateSkill,
  type PublicSkillDetail,
} from "../../../../lib/api";

const authState = vi.hoisted(() => ({
  user: null as null | {
    id: string;
    name: string;
    display_name: string;
    description: string;
    created_at: string;
    last_seen: string;
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

vi.mock("../../../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  forkSkill: vi.fn(),
  addSkillMember: vi.fn(),
  createPage: vi.fn(),
  getMe: vi.fn(),
  getPublicSkill: vi.fn(),
  listAllPages: vi.fn(),
  listAllTables: vi.fn(),
  listFiles: vi.fn(),
  listMySessions: vi.fn(),
  listSkillMembers: vi.fn(),
  removeSkillMember: vi.fn(),
  searchUsers: vi.fn(),
  updateSkill: vi.fn(),
  uploadFile: vi.fn(),
  getActivityTimeline: vi.fn(),
  getEmbeddingProjection: vi.fn(),
  // Tests render the authenticated view of the page; pretend the
  // viewer has a token so insight panels mount as before.
  getToken: vi.fn(() => "test-token"),
}));

vi.mock("../../../../components/viz/ContributorActivityTimeline", () => ({
  default: () => null,
}));
vi.mock("../../../../components/viz/EmbeddingSpaceExplorer", () => ({
  default: () => null,
}));

vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ user: authState.user, loading: false, logout: vi.fn() }),
}));

vi.mock("./AddToWorkspaceButton", () => ({
  default: () => <button type="button">Add to my files</button>,
}));

// Mirrors how AppShell consumes the ShellChromeContext: pulls the page-
// registered shareAction out of context and renders it under a <header>.
// Lets us assert that share buttons surface in the app chrome.
function ShellChromeHarness({ children }: { children: ReactNode }) {
  return (
    <ConfirmDialogProvider>
      <ShellChromeProvider>
        <SharedHeader />
        <main>{children}</main>
      </ShellChromeProvider>
    </ConfirmDialogProvider>
  );
}

function SharedHeader() {
  const { shareAction } = useShellChromeValue();
  return <header>{shareAction}</header>;
}

function renderSkill(ui: ReactNode) {
  return render(ui, { wrapper: ShellChromeHarness });
}

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
    can_write: false,
  };
}

describe("SkillPageClient sharing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      id: "user-1",
      name: "Henry",
      display_name: "Henry",
      description: "",
      created_at: "2026-05-11T00:00:00Z",
      last_seen: "2026-05-11T00:00:00Z",
    };
    window.history.pushState({}, "", "/skills/shared-skill");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(getActivityTimeline).mockResolvedValue({
      contributors: [],
      buckets: [],
    });
    vi.mocked(getEmbeddingProjection).mockResolvedValue({
      points: [],
      stats: { total_embeddings: 0, projected: 0 },
      cached: false,
    });
    vi.mocked(getMe).mockResolvedValue(authState.user!);
    vi.mocked(getPublicSkill).mockResolvedValue(skillDetail());
    vi.mocked(listSkillMembers).mockResolvedValue([
      {
        user_id: "user-2",
        name: "sam",
        display_name: "Sam",
        permission: "write",
        granted_by: "user-1",
        created_at: "2026-05-12T00:00:00Z",
      },
    ]);
    vi.mocked(searchUsers).mockResolvedValue([
      { id: "user-3", name: "alex", display_name: "Alex" },
    ]);
    vi.mocked(updateSkill).mockImplementation(async (_skillId, updates) => ({
      ...skillDetail().skill,
      ...updates,
    }));
    vi.mocked(addSkillMember).mockResolvedValue({
      user_id: "user-3",
      name: "alex",
      display_name: "Alex",
      permission: "read",
      granted_by: "user-1",
      created_at: "2026-05-13T00:00:00Z",
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the Share button in the app header with a copy-link affordance", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    const shareButton = await screen.findByRole("button", { name: "Share" });
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toBeInTheDocument();
    expect(shareButton.closest("header")).not.toBeNull();
    expect(screen.getAllByRole("button", { name: "Share" })).toHaveLength(1);

    fireEvent.click(shareButton);
    // Popover renders a "Copy" button for the public URL; click it.
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/skills/shared-skill`,
      ),
    );
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("copies an agent-readable handoff link from the app header", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    const handoffButton = await screen.findByRole("button", {
      name: "Copy agent handoff link",
    });
    fireEvent.click(handoffButton);

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        `${window.location.origin}/api/v1/skills/shared-skill?format=text`,
      ),
    );
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toHaveTextContent("Copied");
  });

  it("makes private Skills public and unlisted before copying an agent link", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce({
      ...skillDetail({
        access: "private",
        workspace_permission: "none",
        public_permission: "none",
        discoverable: false,
      }),
      can_write: true,
    });

    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Copy agent handoff link" }),
    );

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", {
        workspace_permission: "read",
        public_permission: "read",
        discoverable: false,
      }),
    );
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      `${window.location.origin}/api/v1/skills/shared-skill?format=text`,
    );
    expect(
      screen.getByRole("button", { name: "Copy agent handoff link" }),
    ).toHaveTextContent("Copied");
  });

  it("can make the Skill private from the Share dropdown", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce({
      ...skillDetail({
        access: "public",
        workspace_permission: "write",
        public_permission: "read",
      }),
      can_write: true,
    });

    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Share Shared Skill",
    });
    fireEvent.change(within(dialog).getByLabelText("Visibility"), {
      target: { value: "private" },
    });

    await waitFor(() =>
      expect(updateSkill).toHaveBeenCalledWith("skill-1", {
        workspace_permission: "none",
        public_permission: "none",
        discoverable: false,
      }),
    );
  });

  it("manages explicit Skill members from the Share dropdown", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce({
      ...skillDetail({
        access: "private",
        workspace_permission: "none",
        public_permission: "none",
      }),
      can_write: true,
    });

    renderSkill(<SkillPageClient slug="shared-skill" />);

    fireEvent.click(await screen.findByRole("button", { name: "Share" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Share Shared Skill",
    });

    expect(await within(dialog).findByText("@sam")).toBeInTheDocument();
    expect(listSkillMembers).toHaveBeenCalledWith("skill-1");

    fireEvent.change(within(dialog).getByPlaceholderText("Search users"), {
      target: { value: "alex" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: /Alex/ }));

    await waitFor(() =>
      expect(addSkillMember).toHaveBeenCalledWith("skill-1", "user-3", "read"),
    );
  });

  it("keeps add/create flows behind the single Add things button", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce({
      ...skillDetail({
        access: "private",
        workspace_permission: "read",
        public_permission: "none",
      }),
      can_write: true,
    });

    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(
      await screen.findByRole("button", { name: "+ Add things" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skill settings" })).toHaveAttribute(
      "href",
      "/skills/shared-skill/settings",
    );
    expect(
      screen.queryByPlaceholderText(
        "Paste a link, type a note, or drop a file",
      ),
    ).not.toBeInTheDocument();
  });

  it("does not render skill access as a title badge", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce(
      skillDetail({
        access: "private",
        workspace_permission: "read",
        public_permission: "none",
      }),
    );

    renderSkill(<SkillPageClient slug="shared-skill" />);

    const title = await screen.findByRole("heading", { name: "Shared Skill" });

    expect(title).toHaveTextContent("Shared Skill");
    expect(title).not.toHaveTextContent("workspace");
  });

  it("loads only recent activity for the commit graph", async () => {
    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(
      await screen.findByText("Activity in this skill — last 30 days"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(getActivityTimeline).toHaveBeenCalledWith(
        30,
        "day",
        undefined,
        "skill-1",
      ),
    );
  });

  it("shows the skill author in the detail header", async () => {
    vi.mocked(getPublicSkill).mockResolvedValueOnce(
      skillDetail({ owner_name: "sam", owner_display_name: "Sam" })
    );

    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(await screen.findByText("by Sam")).toBeInTheDocument();
  });

  it("opens single-file skills directly on the file preview", async () => {
    // The primary-item shortcut only fires for a skill with exactly one
    // item. A folder wrapper means "open container" — could grow — so we
    // render bundle chrome for it. This test pins the strict shape.
    const detail = skillDetail({
      description: "<p>One screenshot.</p>",
    });
    detail.items = [
      {
        object_type: "file",
        object_id: "file-1",
        position: 0,
        label: "shot.png",
        inline: {
          name: "shot.png",
          content_type: "image/png",
          size_bytes: 1234,
          url: "https://files.test/shot.png",
        },
      },
    ];
    vi.mocked(getPublicSkill).mockResolvedValueOnce(detail);

    renderSkill(<SkillPageClient slug="shared-skill" />);

    const image = await screen.findByRole("img", { name: "shot.png" });
    expect(image).toHaveAttribute("src", "https://files.test/shot.png");
    expect(screen.getByText("1 item")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Files" })).not.toBeInTheDocument();
    expect(getActivityTimeline).not.toHaveBeenCalled();
    expect(getEmbeddingProjection).not.toHaveBeenCalled();
  });

  it("shows bundle chrome for a file-plus-folder skill (no primary shortcut)", async () => {
    // The folder is an open container — adding more items would invalidate
    // any "this skill IS the file" promise — so we render the bundle list
    // and the viz section, not the file preview.
    const detail = skillDetail({
      description: "<p>Uploaded from shot.png</p>",
    });
    detail.items = [
      {
        object_type: "folder",
        object_id: "folder-1",
        position: 0,
        label: "shot",
        inline: { pages: [], files: [] },
      },
      {
        object_type: "file",
        object_id: "file-1",
        position: 1,
        label: "shot.png",
        inline: {
          name: "shot.png",
          content_type: "image/png",
          size_bytes: 1234,
          url: "https://files.test/shot.png",
        },
      },
    ];
    vi.mocked(getPublicSkill).mockResolvedValueOnce(detail);

    renderSkill(<SkillPageClient slug="shared-skill" />);

    expect(await screen.findByText("2 items")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Files" })).toBeInTheDocument();
  });
});
