import { cleanup, fireEvent, render as renderBase, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceFileBrowser from "./WorkspaceFileBrowser";
import { ConfirmDialogProvider } from "../../ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}
import {
  createTable,
  deleteTable,
  getWorkspaceTree,
  listFiles,
  listSharedWithMe,
  listTables,
} from "../../../lib/api";
import { refreshWorkspaceSidebar } from "../../../lib/skillNavigationCache";

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("../../../lib/api", () => ({
  createFolder: vi.fn(),
  createPage: vi.fn(),
  createTable: vi.fn(),
  deleteFolder: vi.fn(),
  deleteTable: vi.fn(),
  getFolderContents: vi.fn(),
  getWorkspaceTree: vi.fn(),
  listFiles: vi.fn(),
  listSharedWithMe: vi.fn(),
  listTables: vi.fn(),
  restoreItem: vi.fn(),
  trashItem: vi.fn(),
  updateFile: vi.fn(),
  updateFolder: vi.fn(),
  updatePage: vi.fn(),
  updateTable: vi.fn(),
  uploadFileOrPage: vi.fn(),
}));

vi.mock("../../../lib/skillNavigationCache", () => ({
  refreshWorkspaceSidebar: vi.fn(),
}));

vi.mock("../../../lib/filePins", () => ({
  useFilePins: () => ({
    pinnedIds: [],
    pinnedSet: new Set<string>(),
    isPinned: () => false,
    toggle: vi.fn(),
  }),
}));

vi.mock("../../../lib/pins", () => ({
  useWorkspaceRecents: () => [],
}));

const createdAt = "2026-06-03T12:00:00Z";

function table(id: string, name: string, rowCount = 0) {
  return {
    id,
    workspace_id: "ws-1",
    folder_id: null,
    name,
    description: "",
    columns: [],
    views: [],
    created_by: "user-1",
    updated_by: "user-1",
    created_at: createdAt,
    updated_at: createdAt,
    row_count: rowCount,
  };
}

beforeEach(() => {
  localStorage.clear();
  router.push.mockReset();
  vi.mocked(getWorkspaceTree).mockResolvedValue({ folders: [], pages: [] });
  vi.mocked(listFiles).mockResolvedValue([]);
  vi.mocked(listSharedWithMe).mockResolvedValue([]);
  vi.mocked(listTables).mockResolvedValue({ tables: [] });
  vi.mocked(refreshWorkspaceSidebar).mockResolvedValue({
    sessions: [],
    files: { folders: [], pages: [], files: [] },
    skills: [],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("WorkspaceFileBrowser table creation", () => {
  it("creates a blank table from the + New menu", async () => {
    vi.mocked(createTable).mockResolvedValue(table("table-1", "Untitled table"));

    render(<WorkspaceFileBrowser workspaceId="ws-1" folderId={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /\+ New/ }));
    fireEvent.click(screen.getByRole("button", { name: "Table" }));

    await waitFor(() =>
      expect(createTable).toHaveBeenCalledWith("ws-1", "Untitled table")
    );
    expect(refreshWorkspaceSidebar).toHaveBeenCalledWith("ws-1");
    expect(router.push).toHaveBeenCalledWith("/tables/table-1");
  });

  it("shows standalone workspace tables at the root without duplicating CSV-backed tables", async () => {
    vi.mocked(listFiles).mockResolvedValue([
      {
        id: "file-1",
        workspace_id: "ws-1",
        folder_id: null,
        name: "contacts.csv",
        content_type: "text/csv",
        size_bytes: 24,
        url: "",
        app_url: "",
        uploaded_by: "user-1",
        created_at: createdAt,
        linked_table_id: "table-csv",
      },
    ]);
    vi.mocked(listTables).mockResolvedValue({
      tables: [
        table("table-standalone", "Budget", 2),
        table("table-csv", "Contacts from CSV", 1),
      ],
    });

    render(<WorkspaceFileBrowser workspaceId="ws-1" folderId={null} />);

    fireEvent.click(await screen.findByText("Budget"));

    expect(screen.getByText("contacts.csv")).toBeInTheDocument();
    expect(screen.queryByText("Contacts from CSV")).not.toBeInTheDocument();
    expect(router.push).toHaveBeenCalledWith(
      "/tables/table-standalone"
    );
  });

  it("deletes standalone tables with the table API", async () => {
    vi.mocked(listTables).mockResolvedValue({
      tables: [table("table-standalone", "Budget", 2)],
    });
    vi.mocked(deleteTable).mockResolvedValue(undefined);

    render(<WorkspaceFileBrowser workspaceId="ws-1" folderId={null} />);

    await screen.findByText("Budget");
    fireEvent.click(screen.getByLabelText("Delete"));

    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteTable).toHaveBeenCalledWith("ws-1", "table-standalone")
    );
  });
});
