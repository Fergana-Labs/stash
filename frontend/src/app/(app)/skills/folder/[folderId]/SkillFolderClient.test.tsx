import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillFolderClient from "./SkillFolderClient";
import { getFolderContents, getPage, listSkills, updatePage } from "@/lib/api";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useShareAction } from "@/components/ShellChromeContext";
import { ConfirmDialogProvider } from "@/components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const params = vi.hoisted(() => ({
  folderId: "folder-sub",
}));

vi.mock("next/navigation", () => ({
  useParams: () => params,
  useRouter: () => router,
}));

vi.mock("@/lib/api", () => ({
  getFolderContents: vi.fn(),
  getPage: vi.fn(),
  listSkills: vi.fn(),
  setSkillAgentEnabled: vi.fn(),
  updatePage: vi.fn(),
  trashItem: vi.fn(),
}));

const launchPlanSkill = {
  backing: "folder" as const,
  folder_id: "folder-root",
  source_ref: null,
  source_id: null,
  source_name: null,
  name: "Launch Plan",
  description: "A launch helper",
  when_to_use: "Use when planning a launch.",
  version: "1.2",
  mcp_exposed: false,
  file_count: 3,
  updated_at: "2026-08-26T00:00:00Z",
  published: null,
  agent_enabled: true,
};

vi.mock("@/lib/skillNavigationCache", () => ({
  refreshSidebar: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("@/components/ShellChromeContext", () => ({
  useShareAction: vi.fn(),
}));

vi.mock("@/components/share/ResourceShareButton", () => ({
  default: ({ resourceUrlPath }: { resourceUrlPath?: string }) => (
    <button data-share-url={resourceUrlPath}>Share resource</button>
  ),
}));

vi.mock("@/components/content/file-browser/FileBrowser", () => ({
  default: ({
    folderHrefBase,
    hiddenItemIds,
    intro,
    itemsHeading,
    supportingFilesMode,
  }: {
    folderHrefBase?: string;
    hiddenItemIds?: readonly string[];
    intro?: ReactNode;
    itemsHeading?: string;
    supportingFilesMode?: boolean;
  }) => (
    <div
      data-testid="file-browser"
      data-href-base={folderHrefBase}
      data-hidden-items={hiddenItemIds?.join(",")}
      data-supporting-files-mode={supportingFilesMode}
    >
      {intro}
      {itemsHeading}
    </div>
  ),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "henry", display_name: "Henry" },
    loading: false,
  }),
}));

describe("SkillFolderClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSkills).mockResolvedValue([launchPlanSkill]);
    params.folderId = "folder-sub";
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-sub",
        name: "research",
        parent_folder_id: "folder-root",
        is_skill: false,
      },
      breadcrumbs: [
        {
          id: "folder-top",
          name: "Projects",
          is_skill: false,
          is_memory: false,
        },
        {
          id: "folder-root",
          name: "Launch Plan",
          is_skill: true,
          is_memory: false,
        },
        {
          id: "folder-sub",
          name: "research",
          is_skill: false,
          is_memory: false,
        },
      ],
      subfolders: [],
      pages: [],
      files: [],
      tables: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("roots breadcrumbs at Skills and trails from the skill folder", async () => {
    render(<SkillFolderClient folderId="folder-sub" />);

    await screen.findByTestId("file-browser");

    const crumbs = vi.mocked(useBreadcrumbs).mock.calls.at(-1)?.[0];
    // Crumbs point at /skills/folder/<id>, not /skills/<id> — the latter is
    // the published-slug route and renders "Skill not found" for a folder id.
    expect(crumbs).toEqual([
      { label: "Skills", href: "/skills" },
      { label: "Launch Plan", href: "/skills/folder/folder-root" },
      { label: "research" },
    ]);
    // Ancestors above the skill root (plain folders) stay out of the trail.
    expect(crumbs?.some((c: { label: string }) => c.label === "Projects")).toBe(
      false,
    );
  });

  it("keeps folder navigation on the skill browse route", async () => {
    render(<SkillFolderClient folderId="folder-sub" />);

    const browser = await screen.findByTestId("file-browser");
    // FileBrowser builds `${folderHrefBase}/${id}`, so a subfolder inside a
    // skill must resolve to /skills/folder/<id>.
    expect(browser).toHaveAttribute("data-href-base", "/skills/folder");
  });

  it("bounces non-skill folders back to the Files route", async () => {
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-sub",
        name: "plain",
        parent_folder_id: null,
        is_skill: false,
      },
      breadcrumbs: [
        { id: "folder-sub", name: "plain", is_skill: false, is_memory: false },
      ],
      subfolders: [],
      pages: [],
      files: [],
      tables: [],
    });

    render(<SkillFolderClient folderId="folder-sub" />);

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/folders/folder-sub"),
    );
  });

  // The Share dialog turns this path into the link the user copies. Pointing
  // it at /skills/<folderId> hands the recipient a "Skill not found" page.
  it("shares the skill with a link the recipient can open", async () => {
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-root",
        name: "Launch Plan",
        parent_folder_id: null,
        is_skill: true,
      },
      breadcrumbs: [
        {
          id: "folder-root",
          name: "Launch Plan",
          is_skill: true,
          is_memory: false,
        },
      ],
      subfolders: [],
      pages: [
        {
          id: "page-skill",
          name: "SKILL.md",
          content_type: "markdown",
          created_at: "2026-08-26T00:00:00Z",
        },
      ],
      files: [],
      tables: [],
    });
    vi.mocked(getPage).mockResolvedValue({
      id: "page-skill",
      owner_user_id: "user-1",
      folder_id: "folder-root",
      name: "SKILL.md",
      content_type: "markdown",
      content_markdown: "# Launch Plan",
      content_html: "",
      html_layout: "responsive",
      content_hash: null,
      can_write: true,
      created_by: "user-1",
      updated_by: null,
      created_at: "2026-08-26T00:00:00Z",
      updated_at: "2026-08-26T00:00:00Z",
    });

    render(<SkillFolderClient folderId="folder-root" />);
    await screen.findByTestId("file-browser");

    const action = vi.mocked(useShareAction).mock.calls.at(-1)?.[0];
    render(<>{action}</>);

    expect(screen.getByText("Share resource")).toHaveAttribute(
      "data-share-url",
      "/skills/folder/folder-root",
    );
  });

  it("leads with rendered SKILL.md instructions and hides that page from the file list", async () => {
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-root",
        name: "Launch Plan",
        parent_folder_id: null,
        is_skill: true,
      },
      breadcrumbs: [
        {
          id: "folder-root",
          name: "Launch Plan",
          is_skill: true,
          is_memory: false,
        },
      ],
      subfolders: [],
      pages: [
        {
          id: "page-skill",
          name: "SKILL.md",
          content_type: "markdown",
          created_at: "2026-08-26T00:00:00Z",
        },
        {
          id: "page-brief",
          name: "Brief",
          content_type: "markdown",
          created_at: "2026-08-26T00:00:00Z",
        },
      ],
      files: [],
      tables: [],
    });
    vi.mocked(getPage).mockResolvedValue({
      id: "page-skill",
      owner_user_id: "user-1",
      folder_id: "folder-root",
      name: "SKILL.md",
      content_type: "markdown",
      content_markdown:
        "---\nname: Launch Plan\ndescription: A launch helper\n---\n\n## When to use this\nFollow the checklist.",
      content_html: "",
      html_layout: "responsive",
      content_hash: null,
      can_write: true,
      created_by: "user-1",
      updated_by: null,
      created_at: "2026-08-26T00:00:00Z",
      updated_at: "2026-08-26T00:00:00Z",
    });

    render(<SkillFolderClient folderId="folder-root" />);

    expect(
      await screen.findByRole("heading", { name: "When to use this" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Follow the checklist.")).toBeInTheDocument();
    // The repository-style header: description, when-to-use, vitals, switch.
    expect(screen.getByRole("heading", { name: "Launch Plan" })).toBeInTheDocument();
    expect(screen.getByText("A launch helper")).toBeInTheDocument();
    expect(screen.getByText("Use when planning a launch.")).toBeInTheDocument();
    expect(screen.getByText("SKILL.md")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Enabled" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.queryByText(/name: Launch Plan/)).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Edit instructions" }),
    );
    const editor = screen.getByLabelText("Instructions");
    expect(editor).toHaveValue(
      "## When to use this\nFollow the checklist.",
    );

    vi.mocked(updatePage).mockResolvedValue({
      ...(await vi.mocked(getPage).mock.results[0].value),
      content_markdown:
        "---\nname: Launch Plan\ndescription: A launch helper\n---\n\nUse the revised checklist.\n",
    });
    fireEvent.change(editor, { target: { value: "Use the revised checklist." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(updatePage).toHaveBeenCalledWith("page-skill", {
        content:
          "---\nname: Launch Plan\ndescription: A launch helper\n---\n\nUse the revised checklist.\n",
      }),
    );
    expect(screen.getByTestId("file-browser")).toHaveAttribute(
      "data-hidden-items",
      "page-skill",
    );
    expect(screen.getByTestId("file-browser")).toHaveAttribute(
      "data-supporting-files-mode",
      "true",
    );
    expect(screen.getByText("Supporting files")).toBeInTheDocument();
  });
});
