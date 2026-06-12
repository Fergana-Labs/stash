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
  getPublicSkill: vi.fn(),
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

const route = vi.hoisted(() => ({
  search: "",
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ tableId: "table-1" }),
  useRouter: () => ({ push: route.push }),
  useSearchParams: () => new URLSearchParams(route.search),
}));

// The user must be referentially stable across renders, like the real
// useAuth. A fresh object per render re-fires every effect that lists
// `user` in its deps (e.g. the loadRows effect), wiping row state edits.
const authUser = vi.hoisted(() => ({
  id: "user-1",
  name: "Henry",
  display_name: "Henry",
  description: "",
  created_at: "2026-05-31T00:00:00Z",
  last_seen: "2026-05-31T00:00:00Z",
}));

vi.mock("../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: authUser,
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock("../../../components/AppShell", () => ({
  default: ({ children }: { children: ReactNode }) => (
    <div data-testid="app-shell">{children}</div>
  ),
}));

vi.mock("../../../components/workspace/FileViewerHeader", () => ({
  default: ({ title }: { title: string }) => <h1>{title}</h1>,
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
    route.search = "";
    route.push.mockClear();
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

  it("loads the table by ID alone and scopes rows to its canonical workspace", async () => {
    render(<TableEditorPage />);

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    // The URL carries no workspaceId; the table's own workspace_id must
    // drive every workspace-scoped call, so links can never go stale.
    expect(api.getTable).toHaveBeenCalledWith("table-1");
    expect(api.listTableRows).toHaveBeenCalledWith(
      "ws-1",
      "table-1",
      expect.objectContaining({ offset: 0 }),
    );
  });

  it("persists resized column widths", async () => {
    api.updateTableColumn.mockResolvedValue({
      ...table,
      columns: [{ ...table.columns[0], width: 260 }],
    });

    render(<TableEditorPage />);

    const handle = await screen.findByLabelText("Resize Name column");
    await act(async () => {
      fireEvent.pointerDown(handle, { clientX: 100 });
      await Promise.resolve();
    });
    fireEvent.pointerMove(document, { clientX: 180 });
    fireEvent.pointerUp(document, { clientX: 180 });

    await waitFor(() =>
      expect(api.updateTableColumn).toHaveBeenCalledWith("ws-1", "table-1", "name", {
        width: 260,
      }),
    );
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

  it("renders skill-mode tables without the app shell for signed-in users", async () => {
    route.search = "skill=shared-skill";
    api.getPublicSkill.mockResolvedValue({
      skill: {
        id: "skill-1",
        title: "Shared Skill",
        workspace_id: "ws-1",
      },
      workspace_name: "Demo",
      folder_name: "Shared Skill",
      contents: {
        subfolders: [],
        pages: [],
        files: [],
        tables: [
          {
            id: "table-1",
            name: "Prospects",
            description: "",
            columns: table.columns,
            rows: [{ data: { name: "Alice" }, row_order: 0 }],
            folder_path: [],
          },
        ],
      },
      can_write: false,
    });

    render(<TableEditorPage />);

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(screen.queryByTestId("app-shell")).not.toBeInTheDocument();
    expect(api.getTable).not.toHaveBeenCalled();
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

  it("keeps a committed cell edit visible while the save is in flight", async () => {
    const editedRow = {
      ...existingRows[0],
      data: { name: "Alicia" },
    };
    let resolveUpdate: (row: typeof editedRow) => void = () => {};
    const updatePromise = new Promise<typeof editedRow>((resolve) => {
      resolveUpdate = resolve;
    });
    api.updateTableRow.mockReturnValueOnce(updatePromise);

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    fireEvent.change(input, { target: { value: "Alicia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.queryByLabelText("Edit row 1 Name")).not.toBeInTheDocument();
    expect(screen.getByText("Alicia")).toBeInTheDocument();
    expect(screen.queryByText("Alice")).not.toBeInTheDocument();

    await act(async () => {
      resolveUpdate(editedRow);
      await updatePromise;
    });

    expect(screen.getByText("Alicia")).toBeInTheDocument();
    expect(api.updateTableRow).toHaveBeenCalledTimes(1);
  });

  it("does not let a stale row reload hide a committed cell edit", async () => {
    const editedRow = {
      ...existingRows[0],
      data: { name: "Alicia" },
    };
    let resolveReload: (rows: { rows: typeof existingRows; total_count: number; has_more: boolean }) => void = () => {};
    const staleReload = new Promise<{ rows: typeof existingRows; total_count: number; has_more: boolean }>((resolve) => {
      resolveReload = resolve;
    });
    api.updateTableRow.mockResolvedValueOnce(editedRow);

    render(<TableEditorPage />);

    await screen.findByText("Alice");
    api.listTableRows.mockReturnValueOnce(staleReload);
    fireEvent.click(screen.getByText("Filter"));
    await waitFor(() => expect(api.listTableRows).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    fireEvent.change(input, { target: { value: "Alicia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByText("Alicia")).toBeInTheDocument();

    await act(async () => {
      resolveReload({ rows: existingRows, total_count: 2, has_more: false });
      await staleReload;
    });

    expect(screen.getByText("Alicia")).toBeInTheDocument();
    expect(screen.queryByText("Alice")).not.toBeInTheDocument();
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
    await act(async () => {
      await Promise.resolve();
    });

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
    const prompt = vi.fn();
    vi.stubGlobal("prompt", prompt);

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    if (!(input instanceof HTMLInputElement)) throw new Error("Expected cell input");
    input.setSelectionRange(0, input.value.length);
    await act(async () => {
      fireEvent.keyDown(input, { key: "k", metaKey: true });
      await Promise.resolve();
    });
    const linkInput = await screen.findByLabelText("Link URL");
    expect(linkInput).toHaveValue("https://");
    fireEvent.change(linkInput, { target: { value: "https://example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-1", {
        name: linkedValue,
      }),
    );
    expect(prompt).not.toHaveBeenCalled();
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

describe("TableEditorPage block paste from spreadsheets", () => {
  const twoColTable = {
    ...table,
    columns: [
      ...table.columns,
      {
        id: "role",
        name: "Role",
        type: "text",
        order: 1,
        required: false,
        default: null,
        options: null,
      },
    ],
  };

  const twoColRows = [
    { ...existingRows[0], data: { name: "Alice", role: "Dev" } },
    { ...existingRows[1], data: { name: "Bob", role: "PM" } },
  ];

  const pasteInto = (target: Element, text: string) =>
    fireEvent.paste(target, { clipboardData: { getData: () => text } });

  beforeEach(() => {
    vi.clearAllMocks();
    route.search = "";
    api.getTable.mockResolvedValue(twoColTable);
    api.summarizeTableRows.mockResolvedValue({ total_rows: 2, columns: {} });
    api.listTableRows.mockResolvedValue({
      rows: twoColRows,
      total_count: 2,
      has_more: false,
    });
    api.updateTableRow.mockImplementation(
      async (_ws: string, _t: string, rowId: string, data: Record<string, unknown>) => {
        const base = twoColRows.find((r) => r.id === rowId)!;
        return { ...base, data: { ...base.data, ...data } };
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

  it("overwrites cells right and down from the focused cell, dropping extra columns", async () => {
    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    // Sheets puts TSV on the clipboard; the third column has nowhere to go.
    pasteInto(input, "A1\tB1\tdropped\nA2\tB2\tdropped\n");

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-1", {
        name: "A1",
        role: "B1",
      }),
    );
    expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-2", {
      name: "A2",
      role: "B2",
    });
    expect(api.createTableRowsBatch).not.toHaveBeenCalled();
    expect(await screen.findByText("A1")).toBeInTheDocument();
    expect(await screen.findByText("B2")).toBeInTheDocument();
  });

  it("fills a single pasted column downward from a non-first anchor column", async () => {
    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Dev"));
    const input = await screen.findByLabelText("Edit row 1 Role");
    pasteInto(input, "Designer\nSales\n");

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-1", {
        role: "Designer",
      }),
    );
    expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-2", {
      role: "Sales",
    });
  });

  it("appends new rows when the pasted block extends past the last row", async () => {
    const appendedRow = {
      ...createdRow,
      data: { name: "Carol", role: "CTO" },
    };
    api.createTableRowsBatch.mockResolvedValue({ rows: [appendedRow] });

    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Bob"));
    const input = await screen.findByLabelText("Edit row 2 Name");
    pasteInto(input, "Bobby\tCOO\nCarol\tCTO\n");

    await waitFor(() =>
      expect(api.createTableRowsBatch).toHaveBeenCalledWith("ws-1", "table-1", [
        { data: { name: "Carol", role: "CTO" } },
      ]),
    );
    expect(api.updateTableRow).toHaveBeenCalledWith("ws-1", "table-1", "row-2", {
      name: "Bobby",
      role: "COO",
    });
    expect(await screen.findByText("Carol")).toBeInTheDocument();
  });

  it("creates all rows when pasting into an empty tail row", async () => {
    api.createTableRowsBatch.mockResolvedValue({
      rows: [
        { ...createdRow, id: "row-3", data: { name: "Carol", role: "CTO" } },
        { ...createdRow, id: "row-4", data: { name: "Dan", role: "CFO" } },
      ],
    });

    render(<TableEditorPage />);

    const [emptyCell] = await screen.findAllByLabelText(/^Empty row \d+ Name$/);
    fireEvent.click(emptyCell);
    const input = await screen.findByLabelText(/^Edit row \d+ Name$/);
    pasteInto(input, "Carol\tCTO\nDan\tCFO\n");

    await waitFor(() =>
      expect(api.createTableRowsBatch).toHaveBeenCalledWith("ws-1", "table-1", [
        { data: { name: "Carol", role: "CTO" } },
        { data: { name: "Dan", role: "CFO" } },
      ]),
    );
    expect(api.updateTableRow).not.toHaveBeenCalled();
    expect(await screen.findByText("Dan")).toBeInTheDocument();
  });

  it("undoes a block paste one row at a time with command-z", async () => {
    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    pasteInto(input, "A1\tB1\nA2\tB2\n");

    await waitFor(() => expect(screen.getByText("A2")).toBeInTheDocument());

    fireEvent.keyDown(document, { key: "z", metaKey: true });

    await waitFor(() =>
      expect(api.updateTableRow).toHaveBeenLastCalledWith("ws-1", "table-1", "row-2", {
        name: "Bob",
        role: "PM",
      }),
    );
  });

  it("leaves single-value pastes to the native cell input", async () => {
    render(<TableEditorPage />);

    fireEvent.click(await screen.findByText("Alice"));
    const input = await screen.findByLabelText("Edit row 1 Name");
    const notPrevented = pasteInto(input, "just one value");

    expect(notPrevented).toBe(true);
    expect(api.updateTableRow).not.toHaveBeenCalled();
    expect(api.createTableRowsBatch).not.toHaveBeenCalled();
  });
});
