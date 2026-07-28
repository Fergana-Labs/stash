/** A file link handed to someone else must open, not bounce.
 *
 * `stash upload` hands back /f/<id>, and files can carry an "anyone with the
 * link" grant — so the viewer has to attempt the read before deciding anyone
 * is signed out. Redirecting first made every public file link unreachable,
 * and sent people who were signed in elsewhere into a login they didn't need.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FileViewerPage from "./FileClient";

const api = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = "ApiError";
    }
  }
  return {
    ApiError,
    getFile: vi.fn(),
    getFolderContents: vi.fn(),
    getPublicSkill: vi.fn(),
    ingestCsvFile: vi.fn(),
    ingestXlsxFile: vi.fn(),
    trashItem: vi.fn(),
    updateFile: vi.fn(),
  };
});

const route = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), search: "" }));
const auth = vi.hoisted(() => ({ user: null as unknown, loading: false }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: route.push, replace: route.replace }),
  useSearchParams: () => new URLSearchParams(route.search),
}));
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => auth }));
vi.mock("@/lib/api", () => api);
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
vi.mock("@/components/ShellChromeContext", () => ({ useShareAction: vi.fn() }));
vi.mock("@/components/ConfirmDialog", () => ({ useConfirm: () => vi.fn() }));
vi.mock("@/lib/pins", () => ({ recordRecent: vi.fn() }));
vi.mock("@/lib/memory-folder", () => ({
  sectionCrumbs: () => [],
  useMemoryFolderId: () => null,
}));
vi.mock("@/components/SkeletonStates", () => ({
  FileViewerSkeleton: () => <div>Loading file</div>,
}));
vi.mock("@/components/share/ResourceShareButton", () => ({ default: () => null }));
vi.mock("@/components/content/FileViewerHeader", () => ({
  default: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/content/FileContentRenderer", () => ({
  default: () => <div>file contents</div>,
  isImage: () => false,
  isMarkdown: () => false,
  isPdf: () => false,
  isText: () => true,
}));

const PUBLIC_FILE = {
  id: "file-1",
  owner_user_id: "someone-else",
  folder_id: null,
  name: "report.png",
  content_type: "image/png",
  size_bytes: 10,
  url: "https://blob.example/report.png",
  app_url: "/f/file-1",
  uploaded_by: "someone-else",
  created_at: "2026-07-24T00:00:00Z",
};

beforeEach(() => {
  route.push.mockClear();
  route.search = "";
  auth.user = null;
  auth.loading = false;
  api.getFile.mockReset();
});

afterEach(cleanup);

describe("signed-out visitor with a file link", () => {
  it("sees a file that has a public link instead of a login redirect", async () => {
    api.getFile.mockResolvedValue(PUBLIC_FILE);

    render(<FileViewerPage fileId="file-1" />);

    await waitFor(() => expect(screen.getByText("file contents")).toBeTruthy());
    expect(route.push).not.toHaveBeenCalled();
  });

  it("is sent to sign in carrying the file link when the read is refused", async () => {
    api.getFile.mockRejectedValue(new api.ApiError(404, "Not found"));

    render(<FileViewerPage fileId="file-1" />);

    // Without `next` a successful sign-in would land them on the home page,
    // silently losing the link they clicked.
    await waitFor(() =>
      expect(route.push).toHaveBeenCalledWith("/login?next=%2Ff%2Ffile-1"),
    );
  });
});
