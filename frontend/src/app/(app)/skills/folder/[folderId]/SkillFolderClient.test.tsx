import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { EditorView } from "@codemirror/view";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillFolderClient from "./SkillFolderClient";
import {
  createPage,
  getFolderContents,
  getPage,
  listSkills,
  trashItem,
  updatePage,
} from "@/lib/api";
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
const searchParams = vi.hoisted(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useParams: () => params,
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/api", () => ({
  fileDownloadUrl: vi.fn((id: string) => `/api/v1/me/files/${id}/download`),
  createPage: vi.fn(),
  getFolderContents: vi.fn(),
  getPage: vi.fn(),
  listSkills: vi.fn(),
  setSkillAgentEnabled: vi.fn(),
  updatePage: vi.fn(),
  uploadFileOrPage: vi.fn(),
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
    searchParams.delete("page");
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

  it("offers an escape hatch when the Skill cannot be opened", async () => {
    vi.mocked(getFolderContents).mockRejectedValue(
      new Error("This file does not belong to this Skill"),
    );

    render(<SkillFolderClient folderId="folder-root" />);

    expect(await screen.findByText("Skill unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go back to Skills" })).toHaveAttribute(
      "href",
      "/skills",
    );
  });

  // The Share dialog turns this path into the link the user copies. Pointing
  // it at /skills/<folderId> hands the recipient a "Skill not found" page.
  it("keeps sharing in the Skill sidebar instead of creating a shell action row", async () => {
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
    await screen.findByRole("link", { name: "All Skills" });

    expect(screen.getByText("Share resource")).toHaveAttribute(
      "data-share-url",
      "/skills/folder/folder-root",
    );
    expect(vi.mocked(useShareAction)).toHaveBeenLastCalledWith(null);
  });

  it("presents the Skill as a Markdown editor with its files in a sidebar", async () => {
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

    const editor = await screen.findByRole("textbox", { name: "Start typing..." });
    const view = EditorView.findFromDOM(editor.closest(".cm-editor") as HTMLElement);
    expect(view?.state.doc.toString()).toBe(
      "---\nname: Launch Plan\ndescription: A launch helper\n---\n\n## When to use this\nFollow the checklist.",
    );
    expect(editor.querySelector(".cm-live-heading-2")).toHaveTextContent(
      "When to use this",
    );
    expect(editor.querySelector(".cm-live-heading-2")).not.toHaveTextContent("##");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All Skills" })).toHaveAttribute(
      "href",
      "/skills",
    );
    expect(screen.queryByRole("heading", { name: "Launch Plan" })).not.toBeInTheDocument();
    expect(screen.queryByText("A launch helper")).not.toBeInTheDocument();
    expect(screen.getAllByText("SKILL.md")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Brief" })).toHaveAttribute(
      "href",
      "/skills/folder/folder-root?page=page-brief",
    );
    const toolbar = screen.getByRole("toolbar", { name: "Markdown editor" });
    expect(toolbar).toHaveTextContent(/SKILL\.md.*Launch Plan/);
    expect(within(toolbar).getByRole("switch", { name: "Enabled" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(toolbar).getByText("Share resource")).toBeInTheDocument();
    const sidebar = screen.getByRole("complementary");
    expect(within(sidebar).queryByRole("switch", { name: "Enabled" })).not.toBeInTheDocument();
    expect(within(sidebar).queryByText("Share resource")).not.toBeInTheDocument();
    expect(screen.queryByTestId("file-browser")).not.toBeInTheDocument();

    vi.mocked(updatePage).mockResolvedValue({
      ...(await vi.mocked(getPage).mock.results[0].value),
      content_markdown:
        "---\nname: Launch Plan\ndescription: A launch helper\n---\n\nUse the revised checklist.\n",
    });
    view?.dispatch({
      changes: {
        from: 0,
        to: view.state.doc.length,
        insert:
          "---\nname: Launch Plan\ndescription: A launch helper\n---\n\nUse the revised checklist.\n",
      },
    });
    fireEvent.keyDown(window, { key: "s", metaKey: true });

    await waitFor(() =>
      expect(updatePage).toHaveBeenCalledWith("page-skill", {
        content:
          "---\nname: Launch Plan\ndescription: A launch helper\n---\n\nUse the revised checklist.\n",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete Brief" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: 'Delete "Brief"?',
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(trashItem).toHaveBeenCalledWith("page", "page-brief"));
  });

  it("opens a supporting Markdown file inside the same Skill editor", async () => {
    searchParams.set("page", "page-brief");
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
      id: "page-brief",
      owner_user_id: "user-1",
      folder_id: "folder-root",
      name: "Brief",
      content_type: "markdown",
      content_markdown: "# Supporting brief",
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

    const toolbar = await screen.findByRole("toolbar", { name: "Markdown editor" });
    expect(toolbar).toHaveTextContent(/Brief.*Launch Plan/);
    expect(screen.getByRole("complementary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Brief" }).parentElement).toHaveClass(
      "bg-raised",
    );
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();

    vi.mocked(updatePage).mockResolvedValue({
      ...(await vi.mocked(getPage).mock.results[0].value),
      name: "Guide.md",
    });
    fireEvent.click(within(toolbar).getByRole("button", { name: "Rename Brief" }));
    const toolbarRename = await screen.findByRole("textbox", { name: "Rename Brief" });
    fireEvent.change(toolbarRename, { target: { value: "Guide.md" } });
    fireEvent.blur(toolbarRename);
    await waitFor(() =>
      expect(updatePage).toHaveBeenCalledWith("page-brief", { name: "Guide.md" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Rename Brief" }));
    expect(await screen.findByRole("textbox", { name: "Rename Brief" })).toBeInTheDocument();
  });

  it("lets the plus menu create and open a Markdown file", async () => {
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
      content_markdown:
        "---\nname: Launch Plan\ndescription: A launch helper\n---\n\n# Launch Plan",
      content_html: "",
      html_layout: "responsive",
      content_hash: null,
      can_write: true,
      created_by: "user-1",
      updated_by: null,
      created_at: "2026-08-26T00:00:00Z",
      updated_at: "2026-08-26T00:00:00Z",
    });
    vi.mocked(createPage).mockResolvedValue({
      id: "page-notes",
      owner_user_id: "user-1",
      folder_id: "folder-root",
      name: "notes.md",
      content_type: "markdown",
      content_markdown: "",
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

    fireEvent.pointerDown(
      await screen.findByRole("button", { name: "Add to Skill" }),
      { button: 0, ctrlKey: false },
    );
    expect(screen.getByRole("menuitem", { name: "New Markdown file" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Upload file" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "New Markdown file" }));

    await waitFor(() =>
      expect(createPage).toHaveBeenCalledWith("Untitled.md", "folder-root"),
    );
    expect(router.push).toHaveBeenCalledWith(
      "/skills/folder/folder-root?page=page-notes",
    );
  });
});
