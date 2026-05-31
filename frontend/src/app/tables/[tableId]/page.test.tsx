import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TableEditorPage from "./page";

const api = vi.hoisted(() => ({
  fetchAuthed: vi.fn(),
  getPublicStash: vi.fn(),
  getTable: vi.fn(),
  updateTable: vi.fn(),
  deleteTable: vi.fn(),
  addTableColumn: vi.fn(),
  updateTableColumn: vi.fn(),
  deleteTableColumn: vi.fn(),
  reorderTableColumns: vi.fn(),
  listTableRows: vi.fn(),
  searchTableRows: vi.fn(),
  createTableRow: vi.fn(),
  createTableRowsBatch: vi.fn(),
  updateTableRow: vi.fn(),
  deleteTableRow: vi.fn(),
  deleteTableRowsBatch: vi.fn(),
  duplicateTableRow: vi.fn(),
  summarizeTableRows: vi.fn(),
  listAllTables: vi.fn(),
  saveTableView: vi.fn(),
  deleteTableView: vi.fn(),
  setTableEmbeddingConfig: vi.fn(),
  backfillTableEmbeddings: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ tableId: "table-1" }),
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("workspaceId=ws-1"),
}));

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      name: "Henry",
      display_name: "Henry",
      description: "",
      created_at: "2026-05-31T00:00:00Z",
      last_seen: "2026-05-31T00:00:00Z",
    },
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../components/AppShell", () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("../../../components/workspace/FileViewerHeader", () => ({
  default: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

vi.mock("../../../lib/shareModalContext", () => ({
  useShareModal: () => ({ open: vi.fn() }),
}));

vi.mock("../../../lib/api", () => api);

const table = {
  id: "table-1",
  workspace_id: "ws-1",
  name: "Prospects",
  description: "",
  columns: [
    {
      id: "name",
      name: "Name",
      type: "text",
      order: 0,
      required: false,
      default: null,
      options: null,
    },
  ],
  views: [],
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-05-31T00:00:00Z",
  updated_at: "2026-05-31T00:00:00Z",
  row_count: 2,
};

const existingRows = [
  {
    id: "row-1",
    table_id: "table-1",
    data: { name: "Alice" },
    row_order: 0,
    created_by: "user-1",
    updated_by: null,
    created_at: "2026-05-31T00:00:00Z",
    updated_at: "2026-05-31T00:00:00Z",
  },
  {
    id: "row-2",
    table_id: "table-1",
    data: { name: "Bob" },
    row_order: 1,
    created_by: "user-1",
    updated_by: null,
    created_at: "2026-05-31T00:00:00Z",
    updated_at: "2026-05-31T00:00:00Z",
  },
];

const createdRow = {
  id: "row-3",
  table_id: "table-1",
  data: { name: "Joao Nunes" },
  row_order: 2,
  created_by: "user-1",
  updated_by: null,
  created_at: "2026-05-31T00:00:00Z",
  updated_at: "2026-05-31T00:00:00Z",
};

describe("TableEditorPage row creation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getTable.mockResolvedValue(table);
    api.createTableRow.mockResolvedValue(createdRow);
    api.summarizeTableRows.mockResolvedValue({ total_rows: 2, columns: {} });
    api.listTableRows.mockImplementation(
      async (
        _workspaceId: string | null,
        _tableId: string,
        params?: { offset?: number },
      ) => {
        if (params?.offset === 0) {
          return { rows: existingRows, total_count: 2, has_more: false };
        }
        return { rows: [createdRow], total_count: 3, has_more: false };
      },
    );

    class TestIntersectionObserver {
      observe() {}
      disconnect() {}
    }

    vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("keeps pagination in sync when appending a newly-created row", async () => {
    render(<TableEditorPage />);

    expect(await screen.findByText("Alice")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /\+ New row/i }));

    await waitFor(() =>
      expect(api.createTableRow).toHaveBeenCalledWith("ws-1", "table-1", {}),
    );

    expect(screen.queryByText("1 more rows")).not.toBeInTheDocument();
    expect(screen.getAllByText("Joao Nunes")).toHaveLength(1);
    expect(api.listTableRows).not.toHaveBeenCalledWith(
      "ws-1",
      "table-1",
      expect.objectContaining({ offset: 2 }),
    );
  });
});
