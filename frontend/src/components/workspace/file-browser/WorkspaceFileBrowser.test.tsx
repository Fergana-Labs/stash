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
  getFolderContents,
  getTree,
  listFiles,
  listSharedWithMe,
  listTables,
} from "../../../lib/api";
import { refreshSidebar } from "../../../lib/skillNavigationCache";

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
  getTree: vi.fn(),
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
  refreshSidebar: vi.fn(),
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
    owner_user_id: "user-1",
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
  vi.mocked(getTree).mockResolvedValue({ folders: [], pages: [] });
  vi.mocked(listFiles).mockResolvedValue([]);
  vi.mocked(listSharedWithMe).mockResolvedValue([]);
  vi.mocked(listTables).mockResolvedValue({ tables: [] });
  vi.mocked(refreshSidebar).mockResolvedValue({
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

describe("WorkspaceFileBrowser folder links", () => {
  function folderContents() {
    return {
      folder: {
        id: "folder-1",
        name: "Skill folder",
        parent_folder_id: null,
        is_skill: true,
      },
      breadcrumbs: [{ id: "folder-1", name: "Skill folder", is_skill: true }],
      subfolders: [
        { id: "folder-2", name: "Nested", page_count: 0, file_count: 0, created_at: createdAt },
      ],
      pages: [],
      files: [],
      tables: [],
    };
  }

  it("routes folder navigation through folderHrefBase when provided", async () => {
    vi.mocked(getFolderContents).mockResolvedValue(folderContents());

    render(
      <WorkspaceFileBrowser
        folderId="folder-1"
        folderHrefBase="/skills"
      />
    );

    fireEvent.click(await screen.findByText("Nested"));

    expect(router.push).toHaveBeenCalledWith("/skills/folder-2");
  });

  it("defaults folder navigation to the Files folder route", async () => {
    vi.mocked(getFolderContents).mockResolvedValue(folderContents());

    render(<WorkspaceFileBrowser folderId="folder-1" />);

    fireEvent.click(await screen.findByText("Nested"));

    expect(router.push).toHaveBeenCalledWith("/folders/folder-2");
  });
});

describe("WorkspaceFileBrowser table creation", () => {
  it("creates a blank table from the + New menu", async () => {
    vi.mocked(createTable).mockResolvedValue(table("table-1", "Untitled table"));

    render(<WorkspaceFileBrowser folderId={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /\+ New/ }));
    fireEvent.click(screen.getByRole("button", { name: "Table" }));

    await waitFor(() =>
      expect(createTable).toHaveBeenCalledWith("Untitled table")
    );
    expect(refreshSidebar).toHaveBeenCalled();
    expect(router.push).toHaveBeenCalledWith("/tables/table-1");
  });

  it("shows standalone tables at the root without duplicating CSV-backed tables", async () => {
    vi.mocked(listFiles).mockResolvedValue([
      {
        id: "file-1",
        owner_user_id: "user-1",
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

    render(<WorkspaceFileBrowser folderId={null} />);

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

    render(<WorkspaceFileBrowser folderId={null} />);

    await screen.findByText("Budget");
    fireEvent.click(screen.getByLabelText("Delete"));

    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteTable).toHaveBeenCalledWith("table-standalone")
    );
  });
});

