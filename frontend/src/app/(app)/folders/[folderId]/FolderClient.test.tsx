import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FolderClient from "./FolderClient";
import { getFolderContents } from "@/lib/api";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ folderId: "folder-root" }),
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status = 500;
  },
  convertFolderToSkill: vi.fn(),
  getFolderContents: vi.fn(),
  getPublicSkill: vi.fn(),
}));

vi.mock("@/lib/skillNavigationCache", () => ({
  refreshSidebar: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/lib/localSkill", () => ({
  findInSkillContents: vi.fn(() => null),
}));

vi.mock("@/lib/memory-folder", () => ({
  sectionCrumbs: () => [],
  useMemoryFolderId: () => null,
}));

vi.mock("@/components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("@/components/ShellChromeContext", () => ({
  useShareAction: vi.fn(),
}));

vi.mock("@/components/share/ResourceShareButton", () => ({
  default: () => <button>Share resource</button>,
}));

vi.mock("@/components/content/file-browser/FileBrowser", () => ({
  default: () => <div data-testid="file-browser" />,
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: { id: "user-1", name: "henry" }, loading: false }),
}));

function contents(folderIsSkill: boolean, breadcrumbIsSkill = false) {
  return {
    folder: {
      id: "folder-root",
      name: "Brake Shoes",
      parent_folder_id: null,
      is_skill: folderIsSkill,
    },
    breadcrumbs: [{ id: "folder-root", name: "Brake Shoes", is_skill: breadcrumbIsSkill }],
    subfolders: [],
    pages: [],
    files: [],
    tables: [],
  };
}

describe("FolderClient skill redirect", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  // /skills/<x> is the *published slug* route. Sending a folder id there
  // renders "Skill not found" — which is what a user saw right after
  // creating a skill. The skill's own browse page is /skills/folder/<id>.
  it("sends a skill folder to the skill browse route, not the published-slug route", async () => {
    vi.mocked(getFolderContents).mockResolvedValue(contents(true));

    render(<FolderClient folderId="folder-root" />);

    await waitFor(() => expect(router.replace).toHaveBeenCalled());
    expect(router.replace).toHaveBeenCalledWith("/skills/folder/folder-root");
  });

  it("redirects a plain subfolder that lives inside a skill", async () => {
    vi.mocked(getFolderContents).mockResolvedValue(contents(false, true));

    render(<FolderClient folderId="folder-root" />);

    await waitFor(() => expect(router.replace).toHaveBeenCalled());
    expect(router.replace).toHaveBeenCalledWith("/skills/folder/folder-root");
  });

  it("leaves an ordinary folder where it is", async () => {
    vi.mocked(getFolderContents).mockResolvedValue(contents(false));

    render(<FolderClient folderId="folder-root" />);

    await waitFor(() => expect(getFolderContents).toHaveBeenCalled());
    expect(router.replace).not.toHaveBeenCalled();
  });
});
