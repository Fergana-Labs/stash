import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AddToCartridgeModal from "./AddToCartridgeModal";
import {
  createPage,
  listAllPages,
  listAllTables,
  listFiles,
  listMySessions,
  updateCartridge,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  addExternalCartridge: vi.fn(),
  createPage: vi.fn(),
  listAllPages: vi.fn(),
  listAllTables: vi.fn(),
  listFiles: vi.fn(),
  listMySessions: vi.fn(),
  updateCartridge: vi.fn(),
  uploadFile: vi.fn(),
}));

describe("AddToCartridgeModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAllPages).mockResolvedValue({ pages: [] });
    vi.mocked(listAllTables).mockResolvedValue({ tables: [] });
    vi.mocked(listFiles).mockResolvedValue([]);
    vi.mocked(listMySessions).mockResolvedValue([]);
    vi.mocked(createPage).mockResolvedValue({
      id: "page-1",
      workspace_id: "workspace-1",
      folder_id: null,
      name: "example.com/spec",
      content_markdown: "<https://example.com/spec>",
      content_html: "",
      content_type: "markdown",
      html_layout: "responsive",
      created_by: "user-1",
      updated_by: "user-1",
      created_at: "2026-05-11T00:00:00Z",
      updated_at: "2026-05-11T00:00:00Z",
    });
    vi.mocked(updateCartridge).mockResolvedValue({} as Awaited<ReturnType<typeof updateCartridge>>);
  });

  afterEach(() => {
    cleanup();
  });

  it("offers one add surface for existing, URL, file, and note flows", async () => {
    renderModal();

    await screen.findByText("No items in this workspace yet.");
    expect(screen.getByRole("heading", { name: "Add to Stash" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add existing" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Paste URL" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload file" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New note" })).toBeInTheDocument();
  });

  it("adds a pasted URL as a page in the target Stash", async () => {
    const onAdded = vi.fn();
    const onClose = vi.fn();
    renderModal({ onAdded, onClose });

    fireEvent.click(screen.getByRole("button", { name: "Paste URL" }));
    fireEvent.change(screen.getByPlaceholderText("https://example.com/spec"), {
      target: { value: "https://example.com/spec" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add URL" }));

    await waitFor(() =>
      expect(createPage).toHaveBeenCalledWith(
        "workspace-1",
        "example.com/spec",
        undefined,
        "<https://example.com/spec>"
      )
    );
    expect(updateCartridge).toHaveBeenCalledWith("stash-1", {
      items: [
        { object_type: "file", object_id: "file-1", position: 0 },
        { object_type: "page", object_id: "page-1", position: 1 },
      ],
    });
    expect(onAdded).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});

function renderModal({
  onAdded = vi.fn(),
  onClose = vi.fn(),
}: {
  onAdded?: () => void;
  onClose?: () => void;
} = {}) {
  render(
    <AddToCartridgeModal
      open
      onClose={onClose}
      stashId="stash-1"
      workspaceId="workspace-1"
      existingItems={[{ object_type: "file", object_id: "file-1", position: 0 }]}
      onAdded={onAdded}
    />
  );
}
