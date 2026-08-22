import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FilesExplorer, { type Item } from "./files-explorer";
import { getFolderContents, getTree, updateFolder, uploadFileOrPage } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: (selector: (s: { openTab: () => void }) => unknown) =>
    selector({ openTab: vi.fn() }),
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
  getTree: vi.fn(),
  getFolderContents: vi.fn(),
  listFiles: vi.fn().mockResolvedValue([]),
  listTables: vi.fn().mockResolvedValue({ tables: [] }),
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
}));

const MEMORY_FOLDER = "memory-folder-1";

function emptyFolder() {
  return {
    breadcrumbs: [{ id: MEMORY_FOLDER, name: "Memory" }],
    subfolders: [],
    pages: [],
    files: [],
    tables: [],
  };
}

function uploadInto(container: HTMLElement, file: File) {
  const input = container.querySelector('input[type="file"]')!;
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  vi.mocked(getFolderContents).mockResolvedValue(emptyFolder() as never);
  vi.mocked(uploadFileOrPage).mockResolvedValue({ kind: "file" } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Memory is the curator agent's knowledge base: a human writing into it is
// legitimate but unusual, so the explorer must confirm the intent and offer
// Files (the normal destination) as a one-click redirect.
describe("FilesExplorer uploads", () => {
  const file = new File(["hi"], "heavi.md", { type: "text/markdown" });

  it("uploads into the browsed folder immediately", async () => {
    const { container } = render(
      <FilesExplorer onRoot={() => {}} rootLabel="Files" rootFolderId={MEMORY_FOLDER} />
    );
    await screen.findByText("Empty folder.");

    uploadInto(container, file);

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file, MEMORY_FOLDER));
  });
});

// A share is a permission row, never a copy: the things under "Shared with me"
// live in someone else's scope. The node exists so they're reachable at all —
// before it, GET /shares/with-me had no surface in the app — but nothing under
// it may be treated as yours.
describe("FilesExplorer shared node", () => {
  const emptyTree = { folders: [], pages: [] };

  function renderFiles(loadShared?: () => Promise<Item[]>) {
    return render(<FilesExplorer onRoot={() => {}} rootLabel="Files" loadShared={loadShared} />);
  }

  beforeEach(() => {
    vi.mocked(getTree).mockResolvedValue(emptyTree as never);
  });

  it("stays out of the tree when nothing is shared with you", async () => {
    renderFiles(async () => []);

    await screen.findByText("Empty folder.");
    expect(screen.queryByText("Shared with me")).not.toBeInTheDocument();
  });

  it("is absent entirely for a section that has no shared surface", async () => {
    renderFiles(undefined);

    await screen.findByText("Empty folder.");
    expect(screen.queryByText("Shared with me")).not.toBeInTheDocument();
  });

  it("lists shared items under the node, tagged with their owner", async () => {
    renderFiles(async () => [
      { kind: "folder", id: "f1", name: "Q3 plan (Henry)", readOnly: true },
    ]);

    fireEvent.click(await screen.findByText("Shared with me"));

    expect(await screen.findByText("Q3 plan (Henry)")).toBeInTheDocument();
  });

  it("offers no create or import actions inside the shared index", async () => {
    // Every write here targets someone else's scope, so the only outcome the
    // buttons could have is a 403.
    renderFiles(async () => [
      { kind: "folder", id: "f1", name: "Q3 plan (Henry)", readOnly: true },
    ]);

    fireEvent.click(await screen.findByText("Shared with me"));
    await screen.findByText("Q3 plan (Henry)");

    expect(screen.queryByLabelText("New file")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New folder")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Import from GitHub")).not.toBeInTheDocument();
  });

  it("cannot itself be renamed, deleted, moved, or shared", async () => {
    // The node is an index, not a folder: it has no server-side row to rename
    // or delete, and dragging it somewhere would be dragging a UI affordance.
    renderFiles(async () => [
      { kind: "folder", id: "f1", name: "Q3 plan (Henry)", readOnly: true },
    ]);
    const node = await screen.findByText("Shared with me");

    fireEvent.contextMenu(node);

    expect(screen.queryByText("Rename")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
    expect(screen.queryByText("Share")).not.toBeInTheDocument();
    expect(node.closest("[draggable]")).toHaveAttribute("draggable", "false");
  });

  it("takes no drop while you are inside it", async () => {
    // Dropping your own folder "into" Shared with me would mean moving it into
    // someone else's scope. There is no such move — and the list container
    // catches drops the row itself ignores, so the guard has to be there too,
    // or the item gets moved into the sentinel id.
    renderFiles(async () => [
      { kind: "folder", id: "f1", name: "Q3 plan (Henry)", readOnly: true },
    ]);
    fireEvent.click(await screen.findByText("Shared with me"));
    const row = (await screen.findByText("Q3 plan (Henry)")).closest("[draggable]")!;

    fireEvent.drop(row.parentElement!, {
      dataTransfer: { getData: () => JSON.stringify({ kind: "folder", id: "mine", name: "My folder" }) },
    });

    expect(updateFolder).not.toHaveBeenCalled();
  });

  it("offers no Rename or Delete on a shared item", async () => {
    // Rename/Delete hit owner-only endpoints. Offering them would mean showing
    // an action whose only outcome is a 403.
    renderFiles(async () => [
      { kind: "folder", id: "f1", name: "Q3 plan (Henry)", readOnly: true },
    ]);
    fireEvent.click(await screen.findByText("Shared with me"));
    const row = await screen.findByText("Q3 plan (Henry)");

    fireEvent.contextMenu(row);

    expect(screen.queryByText("Rename")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
  });
});

// Memory and Clips are resolved by identity and written into by code the user
// never sees, so the service refuses to rename, move, or delete one. The
// explorer hides those actions rather than offering what will 400.
describe("FilesExplorer protected folders", () => {
  beforeEach(() => {
    vi.mocked(getTree).mockResolvedValue({
      folders: [
        { id: "clips", name: "Clips", updated_at: "", is_protected: true },
        { id: "notes", name: "Notes", updated_at: "", is_protected: false },
      ],
      pages: [],
    } as never);
  });

  it("offers no Rename, Delete, or drag on a protected folder", async () => {
    render(<FilesExplorer onRoot={() => {}} rootLabel="Files" />);
    const clips = await screen.findByText("Clips");

    fireEvent.contextMenu(clips);

    expect(screen.queryByText("Rename")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
    expect(clips.closest("[draggable]")).toHaveAttribute("draggable", "false");
  });

  it("leaves an ordinary folder fully editable", async () => {
    // The guard must not creep: everything else keeps its actions.
    render(<FilesExplorer onRoot={() => {}} rootLabel="Files" />);
    const notes = await screen.findByText("Notes");

    fireEvent.contextMenu(notes);

    expect(screen.getByText("Rename")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
    expect(notes.closest("[draggable]")).toHaveAttribute("draggable", "true");
  });
});
