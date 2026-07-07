import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FilesExplorer from "./files-explorer";
import { getFolderContents, uploadFileOrPage } from "@/lib/api";

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

vi.mock("@/lib/api", () => ({
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
  importGithubSkill: vi.fn(),
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
describe("FilesExplorer memory write confirmation", () => {
  const file = new File(["hi"], "heavi.md", { type: "text/markdown" });

  function renderMemoryExplorer() {
    return render(
      <FilesExplorer
        onRoot={() => {}}
        rootLabel="Memory"
        rootFolderId={MEMORY_FOLDER}
        confirmMemoryWrites
      />
    );
  }

  it("asks before uploading into Memory instead of writing silently", async () => {
    const { container } = renderMemoryExplorer();
    await screen.findByText("Empty folder.");

    uploadInto(container, file);

    await screen.findByText("Add to Memory?");
    expect(uploadFileOrPage).not.toHaveBeenCalled();
  });

  it("uploads into the browsed Memory folder on 'Add to Memory anyway'", async () => {
    const { container } = renderMemoryExplorer();
    await screen.findByText("Empty folder.");

    uploadInto(container, file);
    fireEvent.click(await screen.findByRole("button", { name: "Add to Memory anyway" }));

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file, MEMORY_FOLDER));
  });

  it("redirects the upload to the Files root on 'Add to Files instead'", async () => {
    const { container } = renderMemoryExplorer();
    await screen.findByText("Empty folder.");

    uploadInto(container, file);
    fireEvent.click(await screen.findByRole("button", { name: "Add to Files instead" }));

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file, undefined));
  });

  it("uploads immediately when the explorer is not in Memory", async () => {
    const { container } = render(
      <FilesExplorer onRoot={() => {}} rootLabel="Files" rootFolderId={MEMORY_FOLDER} />
    );
    await screen.findByText("Empty folder.");

    uploadInto(container, file);

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file, MEMORY_FOLDER));
    expect(screen.queryByText("Add to Memory?")).not.toBeInTheDocument();
  });
});
