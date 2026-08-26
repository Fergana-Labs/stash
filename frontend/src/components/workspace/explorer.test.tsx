import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Explorer from "./explorer";
import { listMySessions } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/sessions",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: (selector: (s: { openTab: () => void }) => unknown) =>
    selector({ openTab: vi.fn() }),
}));

vi.mock("@/lib/memory-folder", () => ({ useMemoryFolderId: () => "memory-folder-1" }));

vi.mock("@/lib/integrations", () => ({
  INTEGRATIONS_CHANGED_EVENT: "integrations-changed",
  listIntegrations: vi.fn().mockResolvedValue([]),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), loading: vi.fn() },
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ user: null, loading: false }),
}));

vi.mock("@/components/ConfirmDialog", () => ({
  useConfirm: () => async () => true,
}));

vi.mock("@/components/share/ResourceShareButton", () => ({
  ResourceShareDialog: () => null,
}));

vi.mock("@/lib/api", () => ({
  listMySessions: vi.fn(),
  listSharedWithMe: vi.fn(),
  listSkills: vi.fn().mockResolvedValue([]),
  listSources: vi.fn().mockResolvedValue([]),
  machineFsList: vi.fn().mockResolvedValue([]),
  getTree: vi.fn(),
  getFolderContents: vi.fn(),
  createPage: vi.fn(),
  createFolder: vi.fn(),
  createTable: vi.fn(),
  updateFolder: vi.fn(),
  updatePage: vi.fn(),
  updateFile: vi.fn(),
  updateTable: vi.fn(),
  trashItem: vi.fn(),
  deleteFolder: vi.fn(),
  deleteTable: vi.fn(),
  uploadFileOrPage: vi.fn(),
  importGithubRepo: vi.fn(),
  inspectGithubImport: vi.fn().mockResolvedValue({ skill_dirs: [] }),
  listGithubImportRepos: vi.fn().mockResolvedValue({ connected: false, repos: [] }),
  ApiError: class ApiError extends Error {},
}));

beforeEach(() => {
  // /me/sessions spans every scope the viewer can read, so a teammate's shared
  // session arrives in the same flat list as your own.
  vi.mocked(listMySessions).mockResolvedValue([
    { session_id: "s-1", title: "My session", last_event_at: "2026-07-24T18:00:00Z" },
    { session_id: "s-2", title: "Henry's session", last_event_at: "2026-07-24T19:00:00Z" },
  ] as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Sessions have no container: the tree is the flat list /me/sessions returns,
// which spans every scope the viewer can read. If it only listed the viewer's
// own rows, a teammate's shared session would be invisible here.
describe("Explorer sessions tree", () => {
  it("lists every readable session, including a teammate's", async () => {
    render(<Explorer section="sessions" />);
    expect(await screen.findByText("My session")).toBeTruthy();
    expect(await screen.findByText("Henry's session")).toBeTruthy();
  });
});
