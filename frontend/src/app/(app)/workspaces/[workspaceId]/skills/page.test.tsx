import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceSkillsPage from "./page";
import {
  createFolder,
  createPage,
  listSkills,
  listSkillsSharedWithMe,
  type SharedSkill,
  type Skill,
} from "../../../../../lib/api";
import { skillMdTemplate } from "../../../../../lib/localSkill";
import { ConfirmDialogProvider } from "../../../../../components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ workspaceId: "ws-1" }),
  useRouter: () => router,
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

vi.mock("../../../../../lib/api", () => ({
  API_BASE: "",
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  createFolder: vi.fn(),
  createPage: vi.fn(),
  deleteFolder: vi.fn(),
  forkSkill: vi.fn(),
  listSkills: vi.fn(),
  listSkillsSharedWithMe: vi.fn(),
}));

vi.mock("../../../../../lib/pins", () => ({
  usePins: () => ({
    pinnedIds: [],
    pinnedSet: new Set<string>(),
    toggle: vi.fn(),
  }),
}));

vi.mock("../../../../../lib/skillNavigationCache", () => ({
  refreshWorkspaceSidebar: vi.fn(() => Promise.resolve()),
}));

function skill(overrides: Partial<Skill> = {}): Skill {
  return {
    folder_id: "folder-1",
    name: "Launch Plan",
    description: "How we launch",
    when_to_use: "",
    version: "",
    mcp_exposed: false,
    file_count: 3,
    updated_at: "2026-06-01T00:00:00Z",
    published: null,
    ...overrides,
  };
}

function sharedSkill(overrides: Partial<SharedSkill> = {}): SharedSkill {
  return {
    folder_id: "folder-ext",
    name: "Onboarding",
    description: "How we onboard",
    workspace_id: "ws-2",
    workspace_name: "Henry's Workspace",
    shared_by: "Henry",
    permission: "read",
    slug: null,
    ...overrides,
  };
}

describe("WorkspaceSkillsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    router.push.mockReset();
    vi.mocked(listSkills).mockResolvedValue([
      skill(),
      skill({
        folder_id: "folder-2",
        name: "Research",
        description: "",
        file_count: 1,
        published: {
          id: "skill-2",
          slug: "research",
          discoverable: true,
          cover_image_url: null,
          icon_url: null,
          view_count: 4,
        },
      }),
    ]);
    vi.mocked(listSkillsSharedWithMe).mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders skill folders as cards linking to the skill browse route", async () => {
    render(<WorkspaceSkillsPage />);

    // The name appears in quick-access and the card grid; every instance
    // must link to the workspace skill browse route.
    const launchLinks = (await screen.findAllByText("Launch Plan")).map((el) =>
      el.closest("a"),
    );
    expect(launchLinks.length).toBeGreaterThan(0);
    for (const link of launchLinks) {
      expect(link).toHaveAttribute("href", "/workspaces/ws-1/skills/folder-1");
    }
    expect(screen.getByText("How we launch")).toBeInTheDocument();

    // Unpublished skills badge as Private; published ones say Published.
    expect(screen.getByText("Private")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    const researchLinks = screen
      .getAllByText("Research")
      .map((el) => el.closest("a"));
    for (const link of researchLinks) {
      expect(link).toHaveAttribute("href", "/workspaces/ws-1/skills/folder-2");
    }
  });

  it("lists skill folders shared with you and links by publish state", async () => {
    vi.mocked(listSkillsSharedWithMe).mockResolvedValue([
      sharedSkill(),
      sharedSkill({
        folder_id: "folder-pub",
        name: "Published Guide",
        slug: "published-guide",
      }),
    ]);

    render(<WorkspaceSkillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Shared with you/ }));

    // Unpublished shared skill links to the sharer's folder route (the share
    // grants read); published ones link to the public skill page.
    expect(await screen.findByText("Onboarding")).toBeInTheDocument();
    expect(screen.getAllByText(/shared by Henry/)).toHaveLength(2);
    const viewLinks = screen.getAllByRole("link", { name: "View" });
    expect(viewLinks[0]).toHaveAttribute(
      "href",
      "/workspaces/ws-2/folders/folder-ext",
    );
    expect(viewLinks[1]).toHaveAttribute("href", "/skills/published-guide");
  });

  it("creates a New Skill folder with a SKILL.md and navigates to it", async () => {
    vi.stubGlobal("prompt", vi.fn(() => "My Skill"));
    vi.mocked(createFolder).mockResolvedValue({
      id: "folder-9",
      workspace_id: "ws-1",
      name: "My Skill",
      parent_folder_id: null,
      created_at: "",
      updated_at: "",
    });
    vi.mocked(createPage).mockResolvedValue({ id: "page-9" });

    render(<WorkspaceSkillsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /New Skill/ }));

    await waitFor(() =>
      expect(createFolder).toHaveBeenCalledWith("ws-1", "My Skill"),
    );
    expect(createPage).toHaveBeenCalledWith(
      "ws-1",
      "SKILL.md",
      "folder-9",
      skillMdTemplate("My Skill"),
    );
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith("/workspaces/ws-1/skills/folder-9"),
    );
  });
});
