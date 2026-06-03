import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TableEditorPage from "./TableClient";

const api = vi.hoisted(() => ({
  fetchAuthed: vi.fn(),
  getPublicCartridge: vi.fn(),
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

  it("undoes a committed cell edit with command-z", async () => {
    const editedRow = {
      ...existingRows[0],
      data: { name: "Alicia" },
    };
    api.updateTableRow.mockResolvedValueOnce(editedRow).mockResolvedValueOnce(existingRows[0]);

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    fireEvent.change(input, { target: { value: "Alicia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-1", {
        name: "Alicia",
      }),
    );
    expect(screen.getByText("Alicia")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "z", metaKey: true });

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenLastCalledWith("ws-1", "table-1", "row-1", {
        name: "Alice",
      }),
    );
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("undoes a committed cell edit while another cell editor is focused", async () => {
    const editedRow = {
      ...existingRows[0],
      data: { name: "Alicia" },
    };
    api.updateTableRow.mockResolvedValueOnce(editedRow).mockResolvedValueOnce(existingRows[0]);

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    fireEvent.change(input, { target: { value: "Alicia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("Alicia")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Bob"));
    const nextInput = await screen.findByLabelText("Edit row 2 Name");
    fireEvent.keyDown(nextInput, { key: "z", metaKey: true });

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenLastCalledWith("ws-1", "table-1", "row-1", {
        name: "Alice",
      }),
    );
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("leaves native cell input undo alone when there is no table undo history", async () => {
    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");

    expect(fireEvent.keyDown(input, { key: "z", metaKey: true })).toBe(true);
    expect(api.updateTableRow).not.toHaveBeenCalled();
  });

  it("links selected text in a text cell with command-k", async () => {
    const linkedValue = "[Alice](https://example.com)";
    const linkedRow = {
      ...existingRows[0],
      data: { name: linkedValue },
    };
    api.updateTableRow.mockResolvedValue(linkedRow);
    vi.stubGlobal("prompt", vi.fn(() => "https://example.com"));

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    if (!(input instanceof HTMLInputElement)) throw new Error("Expected cell input");
    input.setSelectionRange(0, input.value.length);
    await act(async () => {
      fireEvent.keyDown(input, { key: "k", metaKey: true });
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-1", {
        name: linkedValue,
      }),
    );
  });

  it("renders markdown links in text cells", async () => {
    api.listTableRows.mockResolvedValue({
      rows: [
        {
          ...existingRows[0],
          data: { name: "[Alice](https://example.com)" },
        },
      ],
      total_count: 1,
      has_more: false,
    });

    render(<TableEditorPage />);

    const link = await screen.findByRole("link", { name: "Alice" });
    expect(link).toHaveAttribute("href", "https://example.com");
  });

  it("creates a row when typing into an empty tail row", async () => {
    const typedRow = {
      ...createdRow,
      id: "row-4",
      data: { name: "Charlie" },
    };
    api.createTableRow.mockResolvedValue(typedRow);

    render(<TableEditorPage />);

    const [emptyCell] = await screen.findAllByLabelText(/^Empty row \d+ Name$/);
    expect(screen.queryByText("\\u2014")).not.toBeInTheDocument();
    fireEvent.click(emptyCell);

    const input = await screen.findByLabelText(/^Edit row \d+ Name$/);
    fireEvent.change(input, { target: { value: "Charlie" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(api.createTableRow).toHaveBeenCalledWith("ws-1", "table-1", {
        name: "Charlie",
      }),
    );
    expect(screen.getByText("Charlie")).toBeInTheDocument();
  });

  it("undoes a row created from the tail row with command-z", async () => {
    const typedRow = {
      ...createdRow,
      id: "row-4",
      data: { name: "Charlie" },
    };
    api.createTableRow.mockResolvedValue(typedRow);

    render(<TableEditorPage />);

    const [emptyCell] = await screen.findAllByLabelText(/^Empty row \d+ Name$/);
    fireEvent.click(emptyCell);

    const input = await screen.findByLabelText(/^Edit row \d+ Name$/);
    fireEvent.change(input, { target: { value: "Charlie" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("Charlie")).toBeInTheDocument());

    fireEvent.keyDown(document, { key: "z", metaKey: true });

    await waitFor(() =>
      expect(api.deleteTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-4"),
    );
    expect(screen.queryByText("Charlie")).not.toBeInTheDocument();
  });

  it("does not create a row when an empty tail row is left blank", async () => {
    render(<TableEditorPage />);

    const [emptyCell] = await screen.findAllByLabelText(/^Empty row \d+ Name$/);
    fireEvent.click(emptyCell);
    fireEvent.blur(await screen.findByLabelText(/^Edit row \d+ Name$/));

    expect(api.createTableRow).not.toHaveBeenCalled();
  });
});
