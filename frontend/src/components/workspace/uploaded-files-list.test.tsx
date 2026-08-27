import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listUploadedItems, uploadFileOrPage } from "@/lib/api";
import UploadedFilesList from "./uploaded-files-list";

const route = vi.hoisted(() => ({ search: "", push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: route.push }),
  useSearchParams: () => new URLSearchParams(route.search),
}));

vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "toast") },
}));

vi.mock("@/lib/api", () => ({
  listUploadedItems: vi.fn(),
  uploadFileOrPage: vi.fn(),
}));

beforeEach(() => {
  route.search = "";
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
      folder_path: [{ id: "folder-1", name: "Research" }],
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
      folder_path: [],
    },
  ]);
  vi.mocked(uploadFileOrPage).mockResolvedValue({ kind: "file" } as never);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UploadedFilesList", () => {
  it("shows folders before their uploaded contents", async () => {
    render(<UploadedFilesList />);

    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByText("evidence.pdf")).toBeInTheDocument();
    expect(screen.queryByText("brief.md")).not.toBeInTheDocument();
    expect(screen.queryByText("Agent memory")).not.toBeInTheDocument();
  });

  it("opens a folder inside the upload index", async () => {
    render(<UploadedFilesList />);

    fireEvent.click(await screen.findByText("Research"));

    expect(route.push).toHaveBeenCalledWith("/files?folder=folder-1");
  });

  it("opens an uploaded page from its folder", async () => {
    route.search = "folder=folder-1";
    render(<UploadedFilesList />);

    fireEvent.click(await screen.findByText("brief.md"));

    expect(route.push).toHaveBeenCalledWith("/p/page-1");
  });

  it("uploads into the open folder", async () => {
    route.search = "folder=folder-1";
    const { container } = render(<UploadedFilesList />);
    await screen.findByText("brief.md");
    const file = new File(["new"], "new.md", { type: "text/markdown" });

    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });

    await waitFor(() => expect(uploadFileOrPage).toHaveBeenCalledWith(file, "folder-1"));
    await waitFor(() => expect(listUploadedItems).toHaveBeenCalledTimes(2));
  });
});
