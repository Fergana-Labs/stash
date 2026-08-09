import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FolderDetailPage from "./FolderClient";
import { getFolderContents } from "@/lib/api";

const router = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({}),
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  convertFolderToSkill: vi.fn(),
  getFolderContents: vi.fn(),
  getPublicSkill: vi.fn(),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "henry", display_name: "Henry" },
    loading: false,
  }),
}));

vi.mock("@/lib/memory-folder", () => ({
  sectionCrumbs: () => [],
  useMemoryFolderId: () => null,
}));

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
  default: () => <button>Share resource</button>,
}));

vi.mock("@/components/content/file-browser/FileBrowser", () => ({
  default: () => <div data-testid="file-browser" />,
}));

describe("FolderDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  // Recurring bug: /skills/<x> is the published-slug route, so sending a
  // folder id there renders "Skill not found". Skill folders must bounce to
  // /skills/folder/<id>.
  it("bounces a skill folder to the skill browse route, not the slug route", async () => {
    vi.mocked(getFolderContents).mockResolvedValue({
      folder: { id: "folder-1", name: "My Skill", parent_folder_id: null, is_skill: true },
      breadcrumbs: [{ id: "folder-1", name: "My Skill", is_skill: true }],
      subfolders: [],
      pages: [],
      files: [],
      tables: [],
    });

    render(<FolderDetailPage folderId="folder-1" />);

    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/skills/folder/folder-1"),
    );
  });
});
