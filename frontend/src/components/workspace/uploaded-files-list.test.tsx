import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listUploadedItems, uploadFileOrPage } from "@/lib/api";
import UploadedFilesList from "./uploaded-files-list";

const replace = vi.fn();
const openTab = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/workspace-store", () => ({
  useWorkspace: (selector: (state: { openTab: typeof openTab }) => unknown) =>
    selector({ openTab }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "toast") },
}));

vi.mock("@/lib/api", () => ({
  listUploadedItems: vi.fn(),
  uploadFileOrPage: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(listUploadedItems).mockResolvedValue([
    {
      kind: "page",
      id: "page-1",
      name: "brief.md",
      content_type: "markdown",
      size_bytes: 14,
      app_url: "/p/page-1",
      uploaded_by: "user-1",
      created_at: "2026-08-26T12:00:00Z",
    },
    {
      kind: "file",
      id: "file-1",
      name: "evidence.pdf",
      content_type: "application/pdf",
      size_bytes: 42,
      app_url: "/f/file-1",
      uploaded_by: "user-1",
      created_at: "2026-08-26T11:00:00Z",
    },
  ]);
  vi.mocked(uploadFileOrPage).mockResolvedValue({ kind: "file" } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UploadedFilesList", () => {
  it("shows only the uploaded items returned by the upload index", async () => {
    render(<UploadedFilesList />);

    expect(await screen.findByText("brief.md")).toBeInTheDocument();
    expect(screen.getByText("evidence.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Agent memory")).not.toBeInTheDocument();
  });

  it("opens an uploaded page without VFS navigation", async () => {
    render(<UploadedFilesList />);

    fireEvent.click(await screen.findByText("brief.md"));

    expect(openTab).toHaveBeenCalledWith("page", "page-1", { title: "brief.md" });
    expect(replace).toHaveBeenCalledWith("/p/page-1");
  });

  it("uploads directly into the flat index", async () => {
    const { container } = render(<UploadedFilesList />);
    await screen.findByText("brief.md");
    const file = new File(["new"], "new.md", { type: "text/markdown" });

    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file));
    await waitFor(() => expect(listUploadedItems).toHaveBeenCalledTimes(2));
  });
});
