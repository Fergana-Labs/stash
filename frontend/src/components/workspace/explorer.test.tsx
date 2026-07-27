import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Explorer from "./explorer";
import {
  listMySessions,
  listSessionFolders,
  listSharedSessionFolderSessions,
  listSharedWithMe,
} from "@/lib/api";

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
  listSessionFolders: vi.fn(),
  listSharedWithMe: vi.fn(),
  listSharedSessionFolderSessions: vi.fn(),
  createSessionFolder: vi.fn(),
  listSkills: vi.fn().mockResolvedValue([]),
  listSources: vi.fn().mockResolvedValue([]),
  listAgents: vi.fn().mockResolvedValue([]),
  createAgent: vi.fn(),
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
  deleteSessionFolder: vi.fn(),
  updateSessionFolder: vi.fn(),
  uploadFileOrPage: vi.fn(),
  importGithubRepo: vi.fn(),
  inspectGithubImport: vi.fn().mockResolvedValue({ skill_dirs: [] }),
  listGithubImportRepos: vi.fn().mockResolvedValue({ connected: false, repos: [] }),
  ApiError: class ApiError extends Error {},
}));

const HENRY_DEFAULT = "henry-default-folder";

function sharedFolder() {
  return {
    object_type: "session_folder",
    object_id: HENRY_DEFAULT,
    name: "Default",
    owner_user_id: "henry-user",
    owner_name: "Henry",
    shared_by: "Henry",
    permission: "read",
  };
}

beforeEach(() => {
  vi.mocked(listSessionFolders).mockResolvedValue([
    { id: "my-default", name: "Default" },
  ] as never);
  vi.mocked(listSharedWithMe).mockResolvedValue([
    sharedFolder(),
    { object_type: "page", object_id: "p1", name: "A page" },
  ] as never);
  // Every session is filed into a folder at upload, so the root's unfiled list
  // is empty — the folder rows are the only way in.
  vi.mocked(listMySessions).mockResolvedValue([] as never);
  vi.mocked(listSharedSessionFolderSessions).mockResolvedValue([
    { session_id: "s-1", title: "Henry's session", last_event_at: "2026-07-24T18:00:00Z" },
  ] as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// A teammate's sessions are readable but reachable only through the folder they
// were filed into. If the sidebar tree lists just your own folders, their
// sessions are invisible here no matter what the share grants.
describe("Explorer sessions tree", () => {
  it("lists session folders shared with you next to your own", async () => {
    render(<Explorer section="sessions" />);

    expect(await screen.findByText("Default (Henry)")).toBeTruthy();
    expect(screen.getByText("Default")).toBeTruthy();
  });

  it("loads a shared folder's sessions from the share endpoint, not your own scope", async () => {
    render(<Explorer section="sessions" />);
    fireEvent.click(await screen.findByText("Default (Henry)"));

    await waitFor(() =>
      expect(listSharedSessionFolderSessions).toHaveBeenCalledWith(HENRY_DEFAULT)
    );
    expect(await screen.findByText("Henry's session")).toBeTruthy();
    expect(vi.mocked(listMySessions).mock.calls.some((c) => c[1] === HENRY_DEFAULT)).toBe(false);
  });

  it("offers no Rename or Delete on a folder someone shared with you", async () => {
    render(<Explorer section="sessions" />);
    fireEvent.contextMenu(await screen.findByText("Default (Henry)"));

    expect(screen.queryByText("Rename")).toBeNull();
    expect(screen.queryByText("Delete")).toBeNull();
  });

  it("keeps Rename and Delete on your own folders", async () => {
    render(<Explorer section="sessions" />);
    fireEvent.contextMenu(await screen.findByText("Default"));

    expect(await screen.findByText("Rename")).toBeTruthy();
    expect(screen.getByText("Delete")).toBeTruthy();
  });
});
