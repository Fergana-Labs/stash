import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillFolderClient from "./SkillFolderClient";
import { getFolderContents, listSkills } from "../../../../../../lib/api";
import { useBreadcrumbs } from "../../../../../../components/BreadcrumbContext";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

const params = vi.hoisted(() => ({
  workspaceId: "ws-1",
  folderId: "folder-sub",
}));

vi.mock("next/navigation", () => ({
  useParams: () => params,
  useRouter: () => router,
}));

vi.mock("../../../../../../lib/api", () => ({
  getFolderContents: vi.fn(),
  listSkills: vi.fn(),
  trashItem: vi.fn(),
}));

vi.mock("../../../../../../lib/skillNavigationCache", () => ({
  refreshWorkspaceSidebar: vi.fn(() => Promise.resolve()),
}));

vi.mock("../../../../../../components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("../../../../../../components/ShellChromeContext", () => ({
  useShareAction: vi.fn(),
}));

vi.mock("../../../../../../components/skill/SkillShareButton", () => ({
  default: () => <button>Share</button>,
}));

vi.mock(
  "../../../../../../components/workspace/file-browser/WorkspaceFileBrowser",
  () => ({
    default: ({ folderHrefBase }: { folderHrefBase?: string }) => (
      <div data-testid="file-browser" data-href-base={folderHrefBase} />
    ),
  }),
);

vi.mock("../../../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "henry", display_name: "Henry" },
    loading: false,
  }),
}));

describe("SkillFolderClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    params.folderId = "folder-sub";
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-sub",
        name: "research",
        parent_folder_id: "folder-root",
        is_skill: false,
      },
      breadcrumbs: [
        { id: "folder-top", name: "Projects", is_skill: false },
        { id: "folder-root", name: "Launch Plan", is_skill: true },
        { id: "folder-sub", name: "research", is_skill: false },
      ],
      subfolders: [],
      pages: [],
      files: [],
      tables: [],
    });
    vi.mocked(listSkills).mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it("roots breadcrumbs at Skills and trails from the skill folder", async () => {
    render(<SkillFolderClient />);

    await screen.findByTestId("file-browser");

    const crumbs = vi.mocked(useBreadcrumbs).mock.calls.at(-1)?.[0];
    expect(crumbs).toEqual([
      { label: "Skills", href: "/workspaces/ws-1/skills" },
      { label: "Launch Plan", href: "/workspaces/ws-1/skills/folder-root" },
      { label: "research" },
    ]);
    // Ancestors above the skill root (plain folders) stay out of the trail.
    expect(crumbs?.some((c: { label: string }) => c.label === "Projects")).toBe(false);
  });

  it("keeps folder navigation on the skill browse route", async () => {
    render(<SkillFolderClient />);

    const browser = await screen.findByTestId("file-browser");
    expect(browser).toHaveAttribute("data-href-base", "/workspaces/ws-1/skills");
  });

  it("bounces non-skill folders back to the Files route", async () => {
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: {
        id: "folder-sub",
        name: "plain",
        parent_folder_id: null,
        is_skill: false,
      },
      breadcrumbs: [{ id: "folder-sub", name: "plain", is_skill: false }],
      subfolders: [],
      pages: [],
      files: [],
      tables: [],
    });

    render(<SkillFolderClient />);

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/workspaces/ws-1/folders/folder-sub"),
    );
  });
});
