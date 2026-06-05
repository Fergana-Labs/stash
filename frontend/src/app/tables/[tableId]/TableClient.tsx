"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type AnchorHTMLAttributes,
  type FormEvent,
  type HTMLAttributes,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
} from "react";
import Markdown from "react-markdown";
import AppShell from "../../../components/AppShell";
import CustomSelect from "../../../components/CustomSelect";
import { downloadBlob } from "../../../components/DownloadMenu";
import { useAuth } from "../../../hooks/useAuth";
import { useEscapeKey } from "../../../hooks/useEscapeKey";
import { useShareModal } from "../../../lib/shareModalContext";
import { SkeletonBlock, TableEditorSkeleton } from "../../../components/SkeletonStates";
import {
  fetchAuthed,
  getPublicCartridge,
  getTable, updateTable,
  deleteTable, addTableColumn, updateTableColumn,
  deleteTableColumn, reorderTableColumns, listTableRows, searchTableRows,
  createTableRow, createTableRowsBatch, updateTableRow, deleteTableRow,
  deleteTableRowsBatch, duplicateTableRow, summarizeTableRows,
  listAllTables, saveTableView, deleteTableView,
  setTableEmbeddingConfig, backfillTableEmbeddings,
} from "../../../lib/api";
import type { Table, TableColumn, TableRow, TableView } from "../../../lib/types";
import FileViewerHeader from "../../../components/workspace/FileViewerHeader";
import { parseCsv, inferColumnType, detectDelimiter } from "../../../lib/csv";

const TYPE_ICONS: Record<string, string> = {
  text: "Aa", number: "#", boolean: "\u2713", date: "\uD83D\uDCC5", datetime: "\uD83D\uDD53",
  url: "\uD83D\uDD17", email: "@", select: "\u25BC", multiselect: "\u2261", json: "{}",
};
const COLUMN_TYPES = ["text", "number", "boolean", "date", "datetime", "url", "email", "select", "multiselect", "json"] as const;
const PAGE_SIZE = 100;
const DRAFT_ROW_COUNT = 20;
const DRAFT_ROW_PREFIX = "draft-row-";
const FILTER_OPS = ["eq", "neq", "gt", "gte", "lt", "lte", "contains", "is_empty", "is_not_empty"] as const;
const COLUMN_TYPE_OPTIONS = COLUMN_TYPES.map((type) => ({ value: type, label: type }));
const FILTER_OP_OPTIONS = FILTER_OPS.map((op) => ({ value: op, label: op }));
const MARKDOWN_LINK_RE = /\[[^\]\n]+\]\([^)]+\)/;
const TABLE_CELL_MARKDOWN_COMPONENTS = {
  p: ({ children }: HTMLAttributes<HTMLParagraphElement>) => <>{children}</>,
  a: ({ href, children }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-brand hover:underline"
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </a>
  ),
};

interface FilterDef { column_id: string; op: string; value: string }
type SummaryData = { total_rows: number; columns: Record<string, { name: string; filled: number; sum?: number; avg?: number; min?: number; max?: number }> };
type TableUndoAction =
  | { kind: "row-create"; row: TableRow }
  | { kind: "row-update"; row: TableRow };
type CellLinkEditorState = {
  value: string;
  selectionStart: number | null;
  selectionEnd: number | null;
  top: number;
  left: number;
};

const LINK_EDITOR_DEFAULT_HREF = "https://";
const LINK_EDITOR_WIDTH = 320;

const isDraftRowId = (rowId: string) => rowId.startsWith(DRAFT_ROW_PREFIX);
const cloneTableRow = (row: TableRow): TableRow => ({ ...row, data: { ...row.data } });

function isTextEntryTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

function canLinkCellText(col: TableColumn) {
  return col.type === "text";
}

function cellInputType(col: TableColumn) {
  if (col.type === "number") return "number";
  if (col.type === "date") return "date";
  if (col.type === "datetime") return "datetime-local";
  return "text";
}

function markdownLinkText(text: string) {
  return text.replace(/([\\[\]])/g, "\\$1");
}

function markdownLinkHref(href: string) {
  return href.replace(/\s/g, "%20").replace(/\)/g, "%29");
}

function linkMarkdownSelection(
  value: string,
  selectionStart: number | null,
  selectionEnd: number | null,
  href: string,
) {
  const hasSelection =
    selectionStart != null && selectionEnd != null && selectionStart !== selectionEnd;
  const start = hasSelection ? Math.min(selectionStart, selectionEnd) : 0;
  const end = hasSelection ? Math.max(selectionStart, selectionEnd) : value.length;
  const label = value.slice(start, end) || href;
  return `${value.slice(0, start)}[${markdownLinkText(label)}](${markdownLinkHref(
    href,
  )})${value.slice(end)}`;
}

function linkEditorPositionFor(input: HTMLInputElement) {
  const rect = input.getBoundingClientRect();
  const viewportPadding = 12;
  const maxLeft = Math.max(viewportPadding, window.innerWidth - LINK_EDITOR_WIDTH - viewportPadding);
  const left = Math.min(Math.max(viewportPadding, rect.left), maxLeft);
  return {
    top: rect.bottom + 6,
    left,
  };
}

interface CellLinkEditorPopoverProps {
  href: string;
  inputRef: RefObject<HTMLInputElement | null>;
  popoverRef: RefObject<HTMLFormElement | null>;
  top: number;
  left: number;
  onCancel: () => void;
  onHrefChange: (href: string) => void;
  onSubmit: () => void;
}

function CellLinkEditorPopover({
  href,
  inputRef,
  popoverRef,
  top,
  left,
  onCancel,
  onHrefChange,
  onSubmit,
}: CellLinkEditorPopoverProps) {
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    onSubmit();
  }

  return (
    <form
      ref={popoverRef}
      role="dialog"
      aria-label="Edit link"
      onSubmit={submit}
      className="fixed z-50 w-[320px] rounded-lg border border-border bg-base p-2 shadow-[0_12px_32px_-10px_rgba(0,0,0,0.35),0_4px_12px_-6px_rgba(0,0,0,0.18)]"
      style={{ top, left }}
    >
      <div className="flex items-center gap-1.5">
        <input
          ref={inputRef}
          aria-label="Link URL"
          value={href}
          onChange={(e) => onHrefChange(e.target.value)}
          placeholder="Paste link or URL"
          className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1.5 text-[13px] text-foreground outline-none focus:border-brand focus:ring-1 focus:ring-brand"
        />
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-2 py-1.5 text-[12.5px] font-medium text-muted hover:bg-raised hover:text-foreground"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!href.trim()}
          className="rounded-md bg-brand px-2.5 py-1.5 text-[12.5px] font-medium text-white hover:bg-brand-hover disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </form>
  );
}

function TableCellText({ value }: { value: string }) {
  if (!MARKDOWN_LINK_RE.test(value)) return <>{value}</>;
  return (
    <Markdown
      allowedElements={["a", "p"]}
      unwrapDisallowed
      components={TABLE_CELL_MARKDOWN_COMPONENTS}
    >
      {value}
    </Markdown>
  );
}

function isTableCellEditorTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return !!target.closest("[data-table-cell-editor]");
}

export default function TableEditorPage() {
  return (
    <Suspense fallback={<TableEditorSkeleton />}>
      <TableEditorPageInner />
    </Suspense>
  );
}

function TableEditorPageInner() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tableId = params.tableId as string;
  const urlWorkspaceId = searchParams.get("workspaceId");
  // Stash mode: `?stash=<slug>` switches the data source to the public
  // stash payload (which the backend gates by stash readability). All
  // mutating UI is hidden in this mode.
  const stashSlug = searchParams.get("stash");
  const readOnly = !!stashSlug;
  const [stashTitle, setStashTitle] = useState<string | null>(null);
  const { user, loading, logout } = useAuth();

  // Core state
  const [resolvedWorkspaceId, setResolvedWorkspaceId] = useState<string | null>(urlWorkspaceId);
  const [table, setTable] = useState<Table | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [error, setError] = useState("");

  // Sort, filter, search
  const [sortBy, setSortBy] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [filters, setFilters] = useState<FilterDef[]>([]);
  const [showFilterBar, setShowFilterBar] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  // Pagination (infinite scroll)
  const [offset, setOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Cell editing
  const [editingCell, setEditingCell] = useState<{ rowId: string; colId: string } | null>(null);
  const [cellValue, setCellValue] = useState("");
  const cellInputRef = useRef<HTMLInputElement>(null);
  const linkHrefInputRef = useRef<HTMLInputElement>(null);
  const linkEditorRef = useRef<HTMLFormElement>(null);
  const [linkEditor, setLinkEditor] = useState<CellLinkEditorState | null>(null);
  const [linkHref, setLinkHref] = useState(LINK_EDITOR_DEFAULT_HREF);
  const undoStackRef = useRef<TableUndoAction[]>([]);
  const undoInFlightRef = useRef(false);

  // Row detail modal
  const [detailRow, setDetailRow] = useState<TableRow | null>(null);
  const [detailValues, setDetailValues] = useState<Record<string, string>>({});

  // Add column dialog
  const [showAddCol, setShowAddCol] = useState(false);
  const [newColName, setNewColName] = useState("");
  const [newColType, setNewColType] = useState("text");
  const [newColOptions, setNewColOptions] = useState("");

  // Column menu, drag, visibility
  const [colMenu, setColMenu] = useState<{ colId: string; x: number; y: number } | null>(null);
  const [colMenuTypeOpen, setColMenuTypeOpen] = useState(false);
  const [dragCol, setDragCol] = useState<string | null>(null);
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set());
  const [showColVisibility, setShowColVisibility] = useState(false);

  // Bulk selection
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());

  // Group by
  const [groupByCol, setGroupByCol] = useState<string>("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Summary
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [showSummary, setShowSummary] = useState(false);

  // Display
  const [wrapCells, setWrapCells] = useState(false);

  // Saved table layouts are persisted by the existing table-view API.
  const [activeViewId, setActiveViewId] = useState<string | null>(null);

  // Embeddings
  const [showEmbeddings, setShowEmbeddings] = useState(false);
  const [embeddingCols, setEmbeddingCols] = useState<Set<string>>(new Set());
  const [embeddingEnabled, setEmbeddingEnabled] = useState(false);
  const [backfillStatus, setBackfillStatus] = useState("");

  // CSV import
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dropping, setDropping] = useState(false);

  const wsId = resolvedWorkspaceId;
  const sortedColumns = table?.columns ? [...table.columns].sort((a, b) => a.order - b.order) : [];
  const visibleColumns = sortedColumns.filter((c) => !hiddenCols.has(c.id));
  const hasMore = rows.length < totalCount;

  const shareModal = useShareModal();

  const rememberUndo = useCallback((action: TableUndoAction) => {
    undoStackRef.current.push(action);
    if (undoStackRef.current.length > 50) undoStackRef.current.shift();
  }, []);

  const undoLastTableAction = useCallback(async () => {
    if (readOnly || undoInFlightRef.current) return;
    const action = undoStackRef.current[undoStackRef.current.length - 1];
    if (!action) return;

    undoInFlightRef.current = true;
    try {
      if (action.kind === "row-update") {
        const restored = await updateTableRow(wsId, tableId, action.row.id, action.row.data);
        setRows((prev) => prev.map((row) => (row.id === restored.id ? restored : row)));
        setDetailRow((prev) => (prev?.id === restored.id ? restored : prev));
      } else {
        await deleteTableRow(wsId, tableId, action.row.id);
        setRows((prev) => prev.filter((row) => row.id !== action.row.id));
        setTotalCount((count) => Math.max(0, count - 1));
        setSelectedRows((prev) => {
          const next = new Set(prev);
          next.delete(action.row.id);
          return next;
        });
      }
      undoStackRef.current.pop();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to undo");
    } finally {
      undoInFlightRef.current = false;
    }
  }, [readOnly, tableId, wsId]);

  useEffect(() => {
    if (readOnly) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== "z") return;
      const isCellEditorTarget = isTableCellEditorTarget(e.target);
      if (isTextEntryTarget(e.target) && !isCellEditorTarget) return;
      if (isCellEditorTarget && undoStackRef.current.length === 0) return;
      e.preventDefault();
      void undoLastTableAction();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [readOnly, undoLastTableAction]);

  useEscapeKey(!!colMenu, () => setColMenu(null));
  useEffect(() => { if (!colMenu) setColMenuTypeOpen(false); }, [colMenu]);
  useEscapeKey(showColVisibility, () => setShowColVisibility(false));
  useEscapeKey(showEmbeddings, () => setShowEmbeddings(false));
  useEscapeKey(showAddCol, () => setShowAddCol(false));
  useEscapeKey(!!detailRow, () => setDetailRow(null));

  // --- Data Loading ---
  const loadTable = useCallback(async () => {
    try {
      if (stashSlug) {
        // Synthesize a Table from the stash's inlined item content. The
        // backend serializes columns + the first 500 rows when the stash
        // is readable; that's the source of truth in stash mode.
        const stash = await getPublicCartridge(stashSlug);
        setStashTitle(stash.cartridge.title);
        const item = stash.items.find(
          (it) => it.object_type === "table" && it.object_id === tableId
        );
        if (!item || !item.inline) {
          setError("Table isn't in this Stash.");
          return;
        }
        const inline = item.inline as {
          description?: string;
          columns?: TableColumn[];
          rows?: { data: Record<string, unknown>; row_order?: number }[];
        };
        const synth: Table = {
          id: tableId,
          workspace_id: stash.cartridge.workspace_id,
          name: item.label || "Table",
          description: inline.description ?? "",
          columns: (inline.columns ?? []).map((c) => ({ ...c })),
          views: [],
          created_at: "",
          updated_at: "",
        } as unknown as Table;
        setResolvedWorkspaceId(stash.cartridge.workspace_id);
        setTable(synth);
        const synthRows: TableRow[] = (inline.rows ?? []).map((r, i) => ({
          id: `stash-${i}`,
          table_id: tableId,
          data: r.data,
          row_order: r.row_order ?? i,
          created_at: "",
          updated_at: "",
          created_by: "",
        } as unknown as TableRow));
        setRows(synthRows);
        setTotalCount(synthRows.length);
        setOffset(synthRows.length);
        return;
      }
      if (resolvedWorkspaceId) {
        setTable(await getTable(resolvedWorkspaceId, tableId));
        return;
      }
      try {
        setTable(await getTable(null, tableId));
      } catch {
        const all = await listAllTables();
        const match = all?.tables?.find((t) => t.id === tableId);
        if (match?.workspace_id) {
          setResolvedWorkspaceId(match.workspace_id);
          setTable(await getTable(match.workspace_id, tableId));
        } else {
          setError("Table not found");
        }
      }
    } catch { setError("Table not found"); }
  }, [tableId, resolvedWorkspaceId, stashSlug]);

  const buildRowParams = useCallback((pageOffset: number) => {
    const p: { sort_by?: string; sort_order?: string; limit?: number; offset?: number; filters?: object[] } = {
      limit: PAGE_SIZE, offset: pageOffset,
    };
    if (sortBy) { p.sort_by = sortBy; p.sort_order = sortOrder; }
    if (filters.length > 0) p.filters = filters;
    return p;
  }, [sortBy, sortOrder, filters]);

  const loadRows = useCallback(async () => {
    // In stash mode the rows are already populated inline by loadTable
    // (the backend caps the inline payload at 500 rows). Search/filter
    // happen client-side from that snapshot.
    if (readOnly) return;
    try {
      if (searchQuery) {
        const res = await searchTableRows(wsId, tableId, searchQuery, { limit: PAGE_SIZE, offset: 0 });
        setRows(res?.rows ?? []); setTotalCount(res?.total_count ?? 0); setOffset(res?.rows?.length ?? 0);
      } else {
        const res = await listTableRows(wsId, tableId, buildRowParams(0));
        setRows(res?.rows ?? []); setTotalCount(res?.total_count ?? 0); setOffset(res?.rows?.length ?? 0);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
  }, [tableId, wsId, buildRowParams, searchQuery, readOnly]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const res = searchQuery
        ? await searchTableRows(wsId, tableId, searchQuery, { limit: PAGE_SIZE, offset })
        : await listTableRows(wsId, tableId, buildRowParams(offset));
      const newRows = res?.rows ?? [];
      setRows((prev) => {
        const existingIds = new Set(prev.map((row) => row.id));
        return [...prev, ...newRows.filter((row) => !existingIds.has(row.id))];
      });
      setOffset((prev) => prev + newRows.length);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
    setLoadingMore(false);
  }, [tableId, wsId, offset, loadingMore, hasMore, buildRowParams, searchQuery]);

  const loadSummary = useCallback(async () => {
    if (!showSummary || readOnly) return;
    try {
      const s = await summarizeTableRows(wsId, tableId, filters.length > 0 ? filters : undefined);
      setSummary(s);
    } catch { /* ignore */ }
  }, [tableId, wsId, filters, showSummary, readOnly]);

  // Stash mode is anonymous-readable, so load eagerly. Workspace mode
  // waits for auth before hitting workspace-scoped endpoints.
  useEffect(() => { if (readOnly || user) loadTable(); }, [readOnly, user, loadTable]);
  useEffect(() => { if ((readOnly || user) && table) loadRows(); }, [readOnly, user, table, loadRows]);
  useEffect(() => { if (user && table) loadSummary(); }, [user, table, loadSummary]);

  // Initialize embedding state from table config
  useEffect(() => {
    if (!table) return;
    const cfg = (table as unknown as Record<string, unknown>).embedding_config as { enabled?: boolean; columns?: string[] } | null;
    if (cfg) {
      setEmbeddingEnabled(!!cfg.enabled);
      setEmbeddingCols(new Set(cfg.columns || []));
    }
  }, [table]);

  // Infinite scroll observer
  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver(([entry]) => { if (entry.isIntersecting) loadMore(); }, { rootMargin: "200px" });
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [loadMore]);

  useEffect(() => {
    if (editingCell && cellInputRef.current) { cellInputRef.current.focus(); cellInputRef.current.select(); }
  }, [editingCell]);

  useEffect(() => {
    if (!colMenu) return;
    // React's onClick stopPropagation runs in the synthetic event system,
    // but this listener is on the native event chain — so without an
    // explicit "is the click inside the menu?" check the listener fires
    // for clicks on the menu's own items and tears the menu down before
    // the inline submenu (e.g. Change type ›) can render.
    const handler = (e: MouseEvent) => {
      const menuEl = document.querySelector("[data-colmenu]");
      if (menuEl && menuEl.contains(e.target as Node)) return;
      setColMenu(null);
    };
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [colMenu]);

  // Debounced search
  useEffect(() => {
    if (!isSearching) return;
    const timer = setTimeout(() => loadRows(), 300);
    return () => clearTimeout(timer);
  }, [searchQuery, isSearching, loadRows]);

  // --- Sort ---
  const handleSort = (colId: string) => {
    if (sortBy === colId) setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    else { setSortBy(colId); setSortOrder("asc"); }
  };

  const addFilter = () => {
    if (sortedColumns.length === 0) return;
    setFilters((prev) => [...prev, { column_id: sortedColumns[0].id, op: "eq", value: "" }]);
    setShowFilterBar(true);
  };
  const updateFilter = (idx: number, field: keyof FilterDef, val: string) => setFilters((prev) => prev.map((f, i) => (i === idx ? { ...f, [field]: val } : f)));
  const removeFilter = (idx: number) => setFilters((prev) => prev.filter((_, i) => i !== idx));

  const handleDelete = async () => {
    if (!confirm("Delete this table and all its data?")) return;
    try {
      await deleteTable(resolvedWorkspaceId, tableId);
      router.push(wsId ? `/workspaces/${wsId}` : "/");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  const handleAddColumn = async () => {
    if (!newColName.trim()) return;
    try {
      const col: { name: string; type: string; options?: string[] } = { name: newColName.trim(), type: newColType };
      if ((newColType === "select" || newColType === "multiselect") && newColOptions.trim()) col.options = newColOptions.split(",").map((o) => o.trim()).filter(Boolean);
      setTable(await addTableColumn(wsId, tableId, col));
      setShowAddCol(false); setNewColName(""); setNewColType("text"); setNewColOptions("");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to add column"); }
  };
  const handleDeleteColumn = async (colId: string) => {
    if (!confirm("Delete this column?")) return;
    try { setTable(await deleteTableColumn(wsId, tableId, colId)); setColMenu(null); } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleRenameColumn = async (colId: string) => {
    const col = sortedColumns.find((c) => c.id === colId);
    if (!col) return;
    const name = prompt("Column name:", col.name);
    if (!name || name === col.name) return;
    try { setTable(await updateTableColumn(wsId, tableId, colId, { name })); setColMenu(null); } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleChangeColumnType = async (colId: string, type: string) => {
    // Existing cell values stay in JSONB as-is; the new type only governs
    // future writes (which the server validator coerces / rejects). The
    // grid renderer treats unparseable values as plain strings, so a bad
    // pick won't break the table — it'll just stop accepting new values.
    try { setTable(await updateTableColumn(wsId, tableId, colId, { type })); setColMenu(null); } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleColumnDrop = async (targetColId: string) => {
    if (!dragCol || dragCol === targetColId) { setDragCol(null); return; }
    const ids = sortedColumns.map((c) => c.id);
    const fromIdx = ids.indexOf(dragCol);
    const toIdx = ids.indexOf(targetColId);
    if (fromIdx === -1 || toIdx === -1) { setDragCol(null); return; }
    ids.splice(fromIdx, 1); ids.splice(toIdx, 0, dragCol); setDragCol(null);
    try { setTable(await reorderTableColumns(wsId, tableId, ids)); } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleAddRow = async () => {
    try {
      const row = await createTableRow(wsId, tableId, {});
      setRows((prev) => [...prev, row]);
      setTotalCount((c) => c + 1);
      rememberUndo({ kind: "row-create", row: cloneTableRow(row) });
    }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to add row"); }
  };
  const handleDeleteRow = async (rowId: string) => {
    try { await deleteTableRow(wsId, tableId, rowId); setRows((prev) => prev.filter((r) => r.id !== rowId)); setTotalCount((c) => c - 1); setSelectedRows((prev) => { const n = new Set(prev); n.delete(rowId); return n; }); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleDuplicateRow = async (rowId: string) => {
    try {
      const row = await duplicateTableRow(wsId, tableId, rowId);
      setRows((prev) => [...prev, row]);
      setTotalCount((c) => c + 1);
      rememberUndo({ kind: "row-create", row: cloneTableRow(row) });
    }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to duplicate"); }
  };
  const handleBulkDelete = async () => {
    if (selectedRows.size === 0 || !confirm(`Delete ${selectedRows.size} rows?`)) return;
    try { await deleteTableRowsBatch(wsId, tableId, Array.from(selectedRows)); setRows((prev) => prev.filter((r) => !selectedRows.has(r.id))); setTotalCount((c) => c - selectedRows.size); setSelectedRows(new Set()); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const startEditing = (rowId: string, colId: string, currentValue: unknown) => {
    if (readOnly) return;
    setLinkEditor(null);
    setEditingCell({ rowId, colId }); setCellValue(currentValue != null ? String(currentValue) : "");
  };
  const commitEdit = useCallback(async (nextValue = cellValue) => {
    if (!editingCell) return;
    setLinkEditor(null);
    const { rowId, colId } = editingCell;
    const col = table?.columns.find((c) => c.id === colId);
    if (isDraftRowId(rowId) && nextValue === "") {
      setEditingCell(null);
      return;
    }
    let typedValue: unknown = nextValue;
    if (col) {
      if (col.type === "number") typedValue = nextValue === "" ? null : Number(nextValue);
      else if (col.type === "boolean") typedValue = nextValue === "true" || nextValue === "1";
    }
    if (isDraftRowId(rowId)) {
      try {
        const created = await createTableRow(wsId, tableId, { [colId]: typedValue });
        setRows((prev) => [...prev, created]);
        setTotalCount((c) => c + 1);
        rememberUndo({ kind: "row-create", row: cloneTableRow(created) });
      } catch (err) { setError(err instanceof Error ? err.message : "Failed to add row"); }
      setEditingCell(null);
      return;
    }
    const previousRow = rows.find((row) => row.id === rowId);
    try {
      const updated = await updateTableRow(wsId, tableId, rowId, { [colId]: typedValue });
      setRows((prev) => prev.map((r) => (r.id === rowId ? updated : r)));
      if (previousRow) rememberUndo({ kind: "row-update", row: cloneTableRow(previousRow) });
    }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    setEditingCell(null);
  }, [cellValue, editingCell, rememberUndo, rows, table, tableId, wsId]);
  const cancelEdit = () => {
    setLinkEditor(null);
    setEditingCell(null);
  };
  const openCellLinkEditor = (input: HTMLInputElement, col: TableColumn) => {
    if (!canLinkCellText(col) || !editingCell) return;
    const position = linkEditorPositionFor(input);
    setLinkHref(LINK_EDITOR_DEFAULT_HREF);
    setLinkEditor({
      value: cellValue,
      selectionStart: input.selectionStart,
      selectionEnd: input.selectionEnd,
      top: position.top,
      left: position.left,
    });
  };
  const cancelCellLink = () => {
    const selectionStart = linkEditor?.selectionStart;
    const selectionEnd = linkEditor?.selectionEnd;
    setLinkEditor(null);
    window.requestAnimationFrame(() => {
      cellInputRef.current?.focus();
      if (selectionStart != null && selectionEnd != null) {
        cellInputRef.current?.setSelectionRange(selectionStart, selectionEnd);
      }
    });
  };
  const submitCellLink = async () => {
    if (!linkEditor) return;
    const trimmedHref = linkHref.trim();
    if (!trimmedHref) return;
    const nextValue = linkMarkdownSelection(
      linkEditor.value,
      linkEditor.selectionStart,
      linkEditor.selectionEnd,
      trimmedHref,
    );
    setCellValue(nextValue);
    await commitEdit(nextValue);
  };

  useEffect(() => {
    if (!linkEditor) return;
    linkHrefInputRef.current?.focus();
    linkHrefInputRef.current?.select();
  }, [linkEditor]);

  useEffect(() => {
    if (!linkEditor) return;
    const handler = (e: MouseEvent) => {
      if (linkEditorRef.current?.contains(e.target as Node)) return;
      if (isTableCellEditorTarget(e.target)) {
        setLinkEditor(null);
        return;
      }
      void commitEdit();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [linkEditor, commitEdit]);

  useEscapeKey(!!linkEditor, cancelCellLink);

  const handleCellInputKeyDown = (
    e: ReactKeyboardEvent<HTMLInputElement>,
    col: TableColumn,
  ) => {
    if (
      canLinkCellText(col) &&
      (e.metaKey || e.ctrlKey) &&
      !e.altKey &&
      !e.shiftKey &&
      e.key.toLowerCase() === "k"
    ) {
      e.preventDefault();
      openCellLinkEditor(e.currentTarget, col);
      return;
    }

    if (e.key === "Enter") void commitEdit();
    if (e.key === "Escape") cancelEdit();
    if (e.key === "Tab") {
      e.preventDefault();
      void commitEdit();
    }
  };

  // --- Row detail ---
  const openDetail = (row: TableRow) => {
    setDetailRow(row);
    const vals: Record<string, string> = {};
    sortedColumns.forEach((c) => { vals[c.id] = row.data[c.id] != null ? String(row.data[c.id]) : ""; });
    setDetailValues(vals);
  };
  const saveDetail = async () => {
    if (!detailRow) return;
    const data: Record<string, unknown> = {};
    sortedColumns.forEach((c) => {
      const v = detailValues[c.id] || "";
      if (c.type === "number") data[c.id] = v === "" ? null : Number(v);
      else if (c.type === "boolean") data[c.id] = v === "true" || v === "1";
      else data[c.id] = v;
    });
    const previousRow = rows.find((row) => row.id === detailRow.id) ?? detailRow;
    try {
      const updated = await updateTableRow(wsId, tableId, detailRow.id, data);
      setRows((prev) => prev.map((r) => (r.id === detailRow.id ? updated : r)));
      rememberUndo({ kind: "row-update", row: cloneTableRow(previousRow) });
      setDetailRow(null);
    }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- Saved layouts ---
  const handleSaveLayout = async () => {
    const name = prompt("Layout name:");
    if (!name) return;
    try {
      const layout = { name, filters: filters.length > 0 ? filters : undefined, sort_by: sortBy || undefined, sort_order: sortBy ? sortOrder : undefined, visible_columns: hiddenCols.size > 0 ? visibleColumns.map((c) => c.id) : undefined };
      const updated = await saveTableView(wsId, tableId, layout);
      setTable(updated);
      const saved = updated.views?.find((v: TableView) => v.name === name);
      if (saved) setActiveViewId(saved.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleLoadLayout = (layout: TableView) => {
    setActiveViewId(layout.id);
    setFilters(layout.filters?.map((f) => ({ column_id: f.column_id, op: f.op, value: f.value || "" })) ?? []);
    setSortBy(layout.sort_by || ""); setSortOrder((layout.sort_order as "asc" | "desc") || "asc");
    if (layout.visible_columns) { const vis = new Set(layout.visible_columns); setHiddenCols(new Set(sortedColumns.filter((c) => !vis.has(c.id)).map((c) => c.id))); } else { setHiddenCols(new Set()); }
    if (layout.filters && layout.filters.length > 0) setShowFilterBar(true); else setShowFilterBar(false);
  };
  const handleDeleteLayout = async (viewId: string) => {
    try { const updated = await deleteTableView(wsId, tableId, viewId); setTable(updated); if (activeViewId === viewId) { setActiveViewId(null); setFilters([]); setSortBy(""); setSortOrder("asc"); setShowFilterBar(false); setHiddenCols(new Set()); } }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- CSV / TSV import ---
  // Shared by the file picker, drag-drop, and clipboard paste. Auto-creates
  // missing columns with inferred types; existing columns are matched by name.
  const importTabular = async (text: string, delimiter: string) => {
    const rows = parseCsv(text, delimiter);
    if (rows.length < 2) { setError("Need a header row plus at least one data row"); return; }
    const headers = rows[0];
    const dataRows = rows.slice(1);

    const existingNames = new Set(sortedColumns.map((c) => c.name));
    let currentTable = table!;
    for (let ci = 0; ci < headers.length; ci++) {
      const name = headers[ci];
      if (!name || existingNames.has(name)) continue;
      const samples = dataRows.slice(0, 50).map((r) => r[ci] ?? "");
      const colType = inferColumnType(samples);
      currentTable = await addTableColumn(wsId, tableId, { name, type: colType });
      existingNames.add(name);
    }
    setTable(currentTable);

    const colIdByHeader: Record<string, string> = {};
    for (const col of currentTable.columns) colIdByHeader[col.name] = col.id;

    const payload: Record<string, unknown>[] = [];
    for (const r of dataRows) {
      const data: Record<string, unknown> = {};
      headers.forEach((h, idx) => {
        const colId = colIdByHeader[h];
        if (!colId) return;
        const raw = r[idx] ?? "";
        // Server coerces raw strings per column type; empty cells become NULL.
        data[colId] = raw === "" ? null : raw;
      });
      payload.push(data);
    }

    for (let i = 0; i < payload.length; i += 5000) {
      await createTableRowsBatch(
        wsId,
        tableId,
        payload.slice(i, i + 5000).map((d) => ({ data: d })),
      );
    }
    await loadRows(); await loadTable();
  };

  const handleCsvImport = async (file: File) => {
    try {
      const text = await file.text();
      await importTabular(text, detectDelimiter(text));
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to import"); }
  };

  const isFileDrag = (e: React.DragEvent) =>
    Array.from(e.dataTransfer.types || []).includes("Files");

  const handleFileDragOver = (e: React.DragEvent) => {
    if (readOnly || !table || !isFileDrag(e)) return;
    e.preventDefault();
    if (!dropping) setDropping(true);
  };

  const handleFileDragLeave = (e: React.DragEvent) => {
    // Only clear when the drag leaves the container, not when crossing
    // child elements (relatedTarget within the container still counts).
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDropping(false);
  };

  const handleFileDrop = async (e: React.DragEvent) => {
    if (readOnly || !table || !isFileDrag(e)) return;
    e.preventDefault();
    setDropping(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!/\.csv$/i.test(file.name) && !file.type.includes("csv")) {
      setError("Drop a .csv file to append rows");
      return;
    }
    await handleCsvImport(file);
  };

  const handlePasteTabular = async (e: React.ClipboardEvent) => {
    if (readOnly || !table || editingCell) return;
    // Ignore pastes inside inputs/textareas/contentEditable (cell editors,
    // search, filter inputs). Only intercept the bare grid container.
    const target = e.target as HTMLElement | null;
    if (target) {
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
    }
    const text = e.clipboardData.getData("text/plain");
    if (!text || !text.includes("\n")) return;
    e.preventDefault();
    try {
      await importTabular(text, detectDelimiter(text));
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to paste"); }
  };
  const handleCsvExport = async () => {
    if (!table || !wsId) return;
    const base = `/api/v1/workspaces/${wsId}/tables`;
    const p = new URLSearchParams();
    if (sortBy) { p.set("sort_by", sortBy); p.set("sort_order", sortOrder); }
    if (filters.length > 0) p.set("filters", JSON.stringify(filters));
    const url = `${base}/${tableId}/export/csv${p.toString() ? "?" + p : ""}`;
    const response = await fetchAuthed(url);
    if (!response.ok) {
      setError("Export failed");
      return;
    }
    const blob = await response.blob();
    downloadBlob(blob, "text/csv", `${table.name.replace(/\s+/g, "_")}.csv`);
  };

  // --- Selection ---
  const toggleSelectAll = () => { if (selectedRows.size === rows.length) setSelectedRows(new Set()); else setSelectedRows(new Set(rows.map((r) => r.id))); };
  const toggleSelectRow = (rowId: string) => { setSelectedRows((prev) => { const n = new Set(prev); if (n.has(rowId)) n.delete(rowId); else n.add(rowId); return n; }); };

  // --- Group by ---
  const groupedRows = (() => {
    if (!groupByCol) return null;
    const groups: Record<string, TableRow[]> = {};
    for (const row of rows) {
      const val = String(row.data[groupByCol] ?? "(empty)");
      if (!groups[val]) groups[val] = [];
      groups[val].push(row);
    }
    return groups;
  })();
  const showDraftRows = !readOnly && !hasMore && !groupedRows;
  const toggleGroupCollapse = (key: string) => setCollapsedGroups((prev) => { const n = new Set(prev); if (n.has(key)) n.delete(key); else n.add(key); return n; });

  // --- Conditional formatting helper ---
  const getCellBg = (col: TableColumn, value: unknown): string => {
    if (col.type !== "number" || value == null || value === "") return "";
    const num = Number(value);
    if (isNaN(num)) return "";
    // Simple quartile coloring for numbers
    const s = summary?.columns[col.id];
    if (!s || s.min == null || s.max == null || s.min === s.max) return "";
    const pct = (num - s.min) / (s.max - s.min);
    if (pct >= 0.75) return "bg-green-500/10";
    if (pct <= 0.25) return "bg-red-500/10";
    return "";
  };

  // Stash-scoped readers can be anonymous when the stash is public; only
  // redirect to /login in workspace mode.
  useEffect(() => { if (!readOnly && !loading && !user) router.push("/login"); }, [readOnly, user, loading, router]);
  if (loading && !readOnly) return <TableEditorSkeleton />;
  if (!user && !readOnly) return null;
  if (!table && !error) {
    if (!user) {
      return (
        <main className="flex min-h-screen flex-col bg-background">
          <TableEditorSkeleton />
        </main>
      );
    }
    return (
      <AppShell user={user} onLogout={logout}>
        <TableEditorSkeleton />
      </AppShell>
    );
  }

  // --- Render row ---
  const renderEditableCell = (rowId: string, rowNumber: number, col: TableColumn, value: unknown, cellBg = "") => {
    const isEditing = editingCell?.rowId === rowId && editingCell?.colId === col.id;
    const startCellEditing = () => { if (!isEditing) startEditing(rowId, col.id, value); };
    return (
      <td key={col.id} className={`px-1 py-0 border-r border-border/50 min-w-[140px] ${cellBg}`} onClick={startCellEditing}>
        {isEditing ? (
          <div data-table-cell-editor>
            {col.type === "boolean" ? (
              <label className="flex items-center h-8 px-2 cursor-pointer"><input aria-label={`Edit row ${rowNumber} ${col.name}`} type="checkbox" checked={cellValue === "true" || cellValue === "1"} onChange={(e) => setCellValue(String(e.target.checked))} onBlur={() => void commitEdit()} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }} className="accent-brand" autoFocus /></label>
            ) : col.type === "select" && col.options ? (
              <CustomSelect
                value={cellValue}
                options={[
                  { value: "", label: "--" },
                  ...col.options.map((opt) => ({ value: opt, label: opt })),
                ]}
                onChange={(next) => void commitEdit(next)}
                ariaLabel={`Edit row ${rowNumber} ${col.name}`}
                className="h-8 w-full rounded border border-brand bg-surface px-2 text-sm font-mono text-foreground"
                menuClassName="text-sm"
                autoFocus
              />
            ) : (
              <input
                aria-label={`Edit row ${rowNumber} ${col.name}`}
                ref={cellInputRef}
                type={cellInputType(col)}
                value={cellValue}
                onChange={(e) => setCellValue(e.target.value)}
                onBlur={() => { if (!linkEditor) void commitEdit(); }}
                onKeyDown={(e) => handleCellInputKeyDown(e, col)}
                className="w-full h-8 px-2 text-sm bg-transparent outline-none ring-1 ring-brand rounded font-mono text-foreground"
              />
            )}
          </div>
        ) : isDraftRowId(rowId) ? (
          <button
            type="button"
            aria-label={`Empty row ${rowNumber} ${col.name}`}
            onClick={(e) => { e.stopPropagation(); startCellEditing(); }}
            className={`${wrapCells ? "min-h-[32px] py-1" : "h-8"} w-full px-2 flex items-center text-left text-sm font-mono text-foreground ${wrapCells ? "whitespace-normal break-words" : "truncate"} cursor-text bg-transparent focus:outline-none focus:ring-1 focus:ring-brand`}
          >
            <span className="text-muted/30">{"\u2014"}</span>
          </button>
        ) : (
          <div className={`${wrapCells ? "min-h-[32px] py-1" : "h-8"} px-2 flex items-center text-sm font-mono text-foreground ${wrapCells ? "whitespace-normal break-words" : "truncate"} cursor-text`}>
            {col.type === "boolean" ? <span className={value ? "text-green-400" : "text-muted"}>{value ? "\u2713" : "\u2717"}</span>
            : col.type === "url" && value ? <a href={String(value)} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline truncate" onClick={(e) => e.stopPropagation()}>{String(value)}</a>
            : <span className={value != null && value !== "" ? "" : "text-muted/30"}>{value != null && value !== "" ? <TableCellText value={String(value)} /> : "\u2014"}</span>}
          </div>
        )}
      </td>
    );
  };

  const renderRow = (row: TableRow, idx: number) => (
    <tr key={row.id} className={`border-b border-border/50 hover:bg-raised/50 transition-colors group ${selectedRows.has(row.id) ? "bg-brand/5" : ""}`}>
      <td className="px-1 py-0 text-center border-r border-border sticky left-0 z-[5] bg-surface"><input type="checkbox" checked={selectedRows.has(row.id)} onChange={() => toggleSelectRow(row.id)} className="accent-brand" /></td>
      <td className="px-2 py-1.5 text-[10px] text-muted text-center border-r border-border font-mono cursor-pointer hover:text-brand sticky left-8 z-[5] bg-surface shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]" onClick={() => openDetail(row)} title="Open row detail">{idx + 1}</td>
      {visibleColumns.map((col) => {
        const value = row.data[col.id];
        const cellBg = showSummary ? getCellBg(col, value) : "";
        return renderEditableCell(row.id, idx + 1, col, value, cellBg);
      })}
      <td className="px-1 py-0" />
      <td className="px-1 py-0 whitespace-nowrap">
        {!readOnly && (
          <>
            <button onClick={() => handleDuplicateRow(row.id)} className="text-xs text-muted/50 hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity px-1" title="Duplicate">\u2398</button>
            <button onClick={() => handleDeleteRow(row.id)} className="text-xs text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1" title="Delete">&times;</button>
          </>
        )}
      </td>
    </tr>
  );

  const renderDraftRow = (idx: number) => {
    const rowNumber = rows.length + idx + 1;
    const rowId = `${DRAFT_ROW_PREFIX}${idx}`;
    return (
      <tr key={rowId} className="border-b border-border/50 hover:bg-raised/30 transition-colors">
        <td className="px-1 py-0 border-r border-border sticky left-0 z-[5] bg-surface" />
        <td className="px-2 py-1.5 text-[10px] text-muted/60 text-center border-r border-border font-mono sticky left-8 z-[5] bg-surface shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">{rowNumber}</td>
        {visibleColumns.map((col) => renderEditableCell(rowId, rowNumber, col, null))}
        <td className="px-1 py-0" />
        <td className="px-1 py-0" />
      </tr>
    );
  };

  const tableUpdatedAt = table?.updated_at
    ? new Date(table.updated_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  const tableContent = (
      <div
        className="relative flex-1 flex flex-col min-h-0 overflow-hidden"
        onPaste={handlePasteTabular}
        onDragOver={handleFileDragOver}
        onDragLeave={handleFileDragLeave}
        onDrop={handleFileDrop}
      >
        {dropping && (
          <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-brand/10 border-2 border-dashed border-brand">
            <div className="rounded-lg bg-surface/95 px-6 py-3 text-sm font-medium text-brand shadow-lg">
              Drop a CSV to append rows
            </div>
          </div>
        )}
        <FileViewerHeader
          icon={<TableGlyph />}
          iconColor="#059669"
          title={table?.name ?? "Table"}
          onRenameTitle={
            table && !readOnly
              ? async (next) => {
                  const updated = await updateTable(resolvedWorkspaceId, tableId, { name: next });
                  setTable(updated);
                  return updated.name;
                }
              : undefined
          }
          readOnly={readOnly}
          readOnlyLabel="read-only · via Stash"
          backLink={
            readOnly && stashSlug
              ? { label: stashTitle ?? "Stash", href: `/cartridges/${stashSlug}` }
              : undefined
          }
          tags={[{ label: "table", tone: "muted" }]}
          meta={[
            `${visibleColumns.length}/${sortedColumns.length} cols`,
            `${totalCount} rows`,
            tableUpdatedAt ? `Updated ${tableUpdatedAt}` : "",
          ].filter(Boolean)}
          downloadOptions={
            table && !readOnly && wsId
              ? [{ label: "CSV (.csv)", onSelect: () => void handleCsvExport() }]
              : undefined
          }
        />
        {/* Toolbar */}
        <div className="mt-2 flex items-center gap-2 px-4 py-2.5 border-y border-border bg-surface flex-shrink-0 flex-wrap">
          {/* Search */}
          <div className="flex-1 max-w-xs">
            <input value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); setIsSearching(true); }} placeholder="Search all columns..." className="w-full px-3 py-1.5 text-xs bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" />
          </div>
          <div className="flex-1" />
          {table && <>
            {!readOnly && <button onClick={addFilter} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Filter</button>}
            {!readOnly && (filters.length > 0 || sortBy) && <button onClick={handleSaveLayout} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Save layout</button>}
            {/* Group by */}
            <CustomSelect
              value={groupByCol}
              options={[
                { value: "", label: "No grouping" },
                ...sortedColumns
                  .filter((c) => c.type === "select" || c.type === "text")
                  .map((c) => ({ value: c.id, label: `Group: ${c.name}` })),
              ]}
              onChange={(next) => { setGroupByCol(next); setCollapsedGroups(new Set()); }}
              className="min-w-[132px] rounded border border-border bg-raised px-2 py-1 text-xs text-foreground"
              menuClassName="text-xs"
            />
            {!readOnly && <button onClick={() => setShowSummary((p) => !p)} className={`text-xs px-2 py-1 rounded ${showSummary ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>Summary</button>}
            {!readOnly && wsId && <button onClick={() => setShowEmbeddings((p) => !p)} className={`text-xs px-2 py-1 rounded ${showEmbeddings ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>Embeddings</button>}
            <button onClick={() => setShowColVisibility((p) => !p)} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Columns</button>
            <button onClick={() => setWrapCells((p) => !p)} className={`text-xs px-2 py-1 rounded ${wrapCells ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>{wrapCells ? "Wrap" : "Compact"}</button>
            {!readOnly && <button onClick={() => fileInputRef.current?.click()} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Import</button>}
            {!readOnly && <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { if (e.target.files?.[0]) handleCsvImport(e.target.files[0]); e.target.value = ""; }} />}
            {!readOnly && selectedRows.size > 0 && <button onClick={handleBulkDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete {selectedRows.size}</button>}
            {!readOnly && wsId && table && (
              <button
                onClick={() =>
                  shareModal.open({
                    workspaceId: wsId,
                    initial: [{ object_type: "table", object_id: table.id, label_override: table.name }],
                  })
                }
                className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised"
              >
                Share
              </button>
            )}
            {!readOnly && <button onClick={handleDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete table</button>}
          </>}
        </div>

        {/* Column visibility popup */}
        {showColVisibility && (
          <div className="px-4 py-2 border-b border-border bg-raised/50 flex flex-wrap gap-2 flex-shrink-0">
            {sortedColumns.map((c) => (
              <label key={c.id} className="flex items-center gap-1 text-xs text-foreground cursor-pointer">
                <input type="checkbox" checked={!hiddenCols.has(c.id)} onChange={() => setHiddenCols((prev) => { const n = new Set(prev); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })} className="accent-brand" />
                {c.name}
              </label>
            ))}
            <button onClick={() => setShowColVisibility(false)} className="text-xs text-muted hover:text-foreground ml-2">Done</button>
          </div>
        )}

        {/* Embedding config popup */}
        {showEmbeddings && wsId && (
          <div className="px-4 py-3 border-b border-border bg-raised/50 flex-shrink-0">
            <div className="flex items-center gap-3 mb-2">
              <label className="flex items-center gap-1.5 text-xs text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={embeddingEnabled}
                  onChange={(e) => setEmbeddingEnabled(e.target.checked)}
                  className="accent-brand"
                />
                Enable semantic search
              </label>
              <button
                onClick={async () => {
                  try {
                    await setTableEmbeddingConfig(wsId, tableId, {
                      enabled: embeddingEnabled,
                      columns: Array.from(embeddingCols),
                    });
                    setBackfillStatus("Config saved");
                    setTimeout(() => setBackfillStatus(""), 2000);
                  } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
                }}
                className="text-xs bg-[var(--color-brand-600)] hover:bg-[var(--color-brand-700)] text-white px-2 py-1 rounded"
              >
                Save
              </button>
              <button
                onClick={async () => {
                  try {
                    const res = await backfillTableEmbeddings(wsId, tableId);
                    setBackfillStatus(`Embedding ${res.embedded} of ${res.total} rows...`);
                    setTimeout(() => setBackfillStatus(""), 5000);
                  } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
                }}
                className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised"
              >
                Backfill all rows
              </button>
              {backfillStatus && <span className="text-xs text-brand">{backfillStatus}</span>}
            </div>
            <div className="text-[10px] text-muted mb-2">Select columns to include in embeddings:</div>
            <div className="flex flex-wrap gap-2">
              {sortedColumns.filter((c) => c.type === "text" || c.type === "url" || c.type === "email" || c.type === "select").map((c) => (
                <label key={c.id} className="flex items-center gap-1 text-xs text-foreground cursor-pointer">
                  <input
                    type="checkbox"
                    checked={embeddingCols.has(c.id)}
                    onChange={() => setEmbeddingCols((prev) => { const n = new Set(prev); if (n.has(c.id)) n.delete(c.id); else n.add(c.id); return n; })}
                    className="accent-brand"
                  />
                  {c.name}
                </label>
              ))}
            </div>
          </div>
        )}

        {/* Saved layout tabs */}
        {table?.views && table.views.length > 0 && (
          <div className="px-4 py-1.5 border-b border-border bg-surface flex items-center gap-1 flex-shrink-0 overflow-x-auto">
            <button onClick={() => { setActiveViewId(null); setFilters([]); setSortBy(""); setSortOrder("asc"); setShowFilterBar(false); setHiddenCols(new Set()); }} className={`px-3 py-1 text-xs rounded ${!activeViewId ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}>All rows</button>
            {table.views.map((layout: TableView) => (
              <div key={layout.id} className="flex items-center group">
                <button onClick={() => handleLoadLayout(layout)} className={`px-3 py-1 text-xs rounded ${activeViewId === layout.id ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}>{layout.name}</button>
                <button onClick={() => handleDeleteLayout(layout.id)} className="text-[10px] text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 -ml-1">&times;</button>
              </div>
            ))}
            <button onClick={handleSaveLayout} className="px-2 py-1 text-xs text-muted hover:text-brand">+ Save layout</button>
          </div>
        )}

        {/* Filter bar */}
        {showFilterBar && filters.length > 0 && (
          <div className="px-4 py-2 border-b border-border bg-raised/50 flex flex-wrap items-center gap-2 flex-shrink-0">
            {filters.map((f, idx) => (
              <div key={idx} className="flex items-center gap-1 bg-surface border border-border rounded px-2 py-1 text-xs">
                <CustomSelect
                  value={f.column_id}
                  options={sortedColumns.map((c) => ({ value: c.id, label: c.name }))}
                  onChange={(next) => updateFilter(idx, "column_id", next)}
                  className="min-w-[110px] bg-transparent px-1 py-0.5 text-foreground"
                  menuClassName="text-xs"
                />
                <CustomSelect
                  value={f.op}
                  options={FILTER_OP_OPTIONS}
                  onChange={(next) => updateFilter(idx, "op", next)}
                  className="min-w-[96px] bg-transparent px-1 py-0.5 text-muted"
                  menuClassName="text-xs"
                />
                {f.op !== "is_empty" && f.op !== "is_not_empty" && <input value={f.value} onChange={(e) => updateFilter(idx, "value", e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") loadRows(); }} className="w-24 bg-transparent outline-none text-foreground border-b border-border" placeholder="value" />}
                <button onClick={() => removeFilter(idx)} className="text-muted hover:text-red-400 ml-1">&times;</button>
              </div>
            ))}
            <button onClick={addFilter} className="text-xs text-brand hover:text-brand-hover">+ Add</button>
            <button onClick={() => { setFilters([]); setShowFilterBar(false); }} className="text-xs text-muted hover:text-foreground ml-2">Clear all</button>
          </div>
        )}

        {error && <p className="text-red-400 text-sm px-4 py-2 flex-shrink-0">{error}</p>}

        {/* Grid */}
        {table && (
          <div className="flex-1 overflow-auto">
            <table className="w-full border-collapse min-w-max">
              <thead className="sticky top-0 z-10">
                <tr className="bg-surface border-b border-border">
                  <th className="w-8 px-1 py-2 text-center border-r border-border sticky left-0 z-20 bg-surface"><input type="checkbox" checked={selectedRows.size === rows.length && rows.length > 0} onChange={toggleSelectAll} className="accent-brand" /></th>
                  <th className="w-10 px-2 py-2 text-[10px] font-medium text-muted text-center border-r border-border sticky left-8 z-20 bg-surface shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">#</th>
                  {visibleColumns.map((col) => (
                    <th
                      key={col.id}
                      className={`px-3 py-2 text-left text-xs font-medium text-muted border-r border-border min-w-[140px] select-none cursor-pointer hover:bg-raised transition-colors ${dragCol === col.id ? "opacity-50" : ""}`}
                      draggable={!readOnly}
                      onDragStart={() => { if (!readOnly) setDragCol(col.id); }}
                      onDragOver={(e) => { if (!readOnly) e.preventDefault(); }}
                      onDrop={() => { if (!readOnly) handleColumnDrop(col.id); }}
                      onDragEnd={() => setDragCol(null)}
                      onContextMenu={(e) => { if (readOnly) return; e.preventDefault(); setColMenu({ colId: col.id, x: e.clientX, y: e.clientY }); }}
                    >
                      <span className="flex items-center gap-1.5" onClick={() => handleSort(col.id)}>
                        <span className="text-[10px] text-muted/60 font-mono">{TYPE_ICONS[col.type] || "?"}</span>
                        {col.name}
                        {sortBy === col.id && <span className="text-brand text-[10px]">{sortOrder === "asc" ? "\u25B2" : "\u25BC"}</span>}
                      </span>
                    </th>
                  ))}
                  <th className="w-10 px-2 py-2 border-r border-border">
                    {!readOnly && <button onClick={() => setShowAddCol(true)} className="w-6 h-6 rounded bg-raised hover:bg-brand/15 text-muted hover:text-brand text-sm font-bold">+</button>}
                  </th>
                  <th className="w-16" />
                </tr>
              </thead>
              <tbody>
                {groupedRows ? (
                  Object.entries(groupedRows).map(([groupKey, groupRows]) => (
                    <> {/* Group header */}
                      <tr key={`group-${groupKey}`} className="bg-raised/50 border-b border-border cursor-pointer" onClick={() => toggleGroupCollapse(groupKey)}>
                        <td colSpan={visibleColumns.length + 4} className="px-4 py-2 text-xs font-medium text-foreground">
                          <span className="mr-2">{collapsedGroups.has(groupKey) ? "\u25B6" : "\u25BC"}</span>
                          {groupKey} <span className="text-muted ml-2">({groupRows.length})</span>
                        </td>
                      </tr>
                      {!collapsedGroups.has(groupKey) && groupRows.map((row, idx) => renderRow(row, idx))}
                    </>
                  ))
                ) : (
                  <>
                    {rows.map((row, idx) => renderRow(row, idx))}
                    {showDraftRows && Array.from({ length: DRAFT_ROW_COUNT }, (_, idx) => renderDraftRow(idx))}
                  </>
                )}
              </tbody>
              {/* Summary row */}
              {showSummary && summary && (
                <tfoot className="sticky bottom-0 z-10">
                  <tr className="bg-surface border-t-2 border-border">
                    <td className="px-1 py-2 text-center border-r border-border sticky left-0 bg-surface" />
                    <td className="px-2 py-2 text-[10px] text-muted text-center border-r border-border font-mono sticky left-8 bg-surface">\u03A3</td>
                    {visibleColumns.map((col) => {
                      const s = summary.columns[col.id];
                      return (
                        <td key={col.id} className="px-2 py-1.5 border-r border-border text-[10px] font-mono text-muted">
                          {s ? (
                            s.sum != null ? (
                              <div className="space-y-0.5">
                                <div>sum: {s.sum.toLocaleString()}</div>
                                <div>avg: {s.avg}</div>
                                <div>{s.min} — {s.max}</div>
                              </div>
                            ) : (
                              <div>{s.filled}/{summary.total_rows} filled</div>
                            )
                          ) : null}
                        </td>
                      );
                    })}
                    <td /><td />
                  </tr>
                </tfoot>
              )}
            </table>

            {/* Add row + infinite scroll sentinel */}
            {!readOnly && <button onClick={handleAddRow} className="w-full py-2 text-sm text-muted hover:text-foreground hover:bg-raised border-b border-border/50 transition-colors text-left px-4">+ New row</button>}
            {hasMore && (
              <div ref={sentinelRef} className="py-4 text-center text-xs text-muted">
                {loadingMore ? (
                  <SkeletonBlock className="mx-auto h-4 w-32" />
                ) : (
                  `${totalCount - offset} more rows`
                )}
              </div>
            )}
          </div>
        )}

        {linkEditor && (
          <CellLinkEditorPopover
            href={linkHref}
            inputRef={linkHrefInputRef}
            popoverRef={linkEditorRef}
            top={linkEditor.top}
            left={linkEditor.left}
            onCancel={cancelCellLink}
            onHrefChange={setLinkHref}
            onSubmit={() => void submitCellLink()}
          />
        )}

        {/* Column context menu */}
        {colMenu && (
          <div data-colmenu className="fixed z-50 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[180px]" style={{ left: colMenu.x, top: colMenu.y }} onClick={(e) => e.stopPropagation()}>
            {!colMenuTypeOpen ? (
              <>
                <button onClick={() => { handleSort(colMenu.colId); setColMenu(null); }} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Sort {sortBy === colMenu.colId && sortOrder === "asc" ? "descending" : "ascending"}</button>
                <button onClick={() => handleRenameColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Rename</button>
                <button onClick={() => setColMenuTypeOpen(true)} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised flex items-center justify-between">
                  <span>Change type</span>
                  <span className="text-[10px] text-muted font-mono">{sortedColumns.find((c) => c.id === colMenu.colId)?.type ?? ""} ›</span>
                </button>
                <button onClick={() => { setHiddenCols((prev) => new Set([...prev, colMenu.colId])); setColMenu(null); }} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Hide column</button>
                <button onClick={() => handleDeleteColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-red-400 hover:bg-raised">Delete column</button>
              </>
            ) : (
              <>
                <button onClick={() => setColMenuTypeOpen(false)} className="w-full text-left px-3 py-1.5 text-xs text-muted hover:text-foreground hover:bg-raised">‹ Back</button>
                {COLUMN_TYPES.map((t) => {
                  const current = sortedColumns.find((c) => c.id === colMenu.colId)?.type;
                  return (
                    <button
                      key={t}
                      onClick={() => { void handleChangeColumnType(colMenu.colId, t); setColMenuTypeOpen(false); }}
                      className={`w-full text-left px-3 py-1.5 text-sm hover:bg-raised flex items-center gap-2 ${current === t ? "text-brand" : "text-foreground"}`}
                    >
                      <span className="text-[10px] text-muted font-mono w-4 text-center">{TYPE_ICONS[t] ?? "?"}</span>
                      <span>{t}</span>
                      {current === t && <span className="ml-auto text-brand">✓</span>}
                    </button>
                  );
                })}
              </>
            )}
          </div>
        )}

        {/* Add column dialog */}
        {showAddCol && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddCol(false)}>
            <div className="bg-surface border border-border rounded-xl p-6 w-[360px] shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-base font-bold font-display text-foreground mb-4">Add Column</h2>
              <div className="space-y-3">
                <div><label className="text-xs text-muted mb-1 block">Name</label><input value={newColName} onChange={(e) => setNewColName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleAddColumn(); }} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" autoFocus placeholder="Column name" /></div>
                <div>
                  <label className="text-xs text-muted mb-1 block">Type</label>
                  <CustomSelect
                    value={newColType}
                    options={COLUMN_TYPE_OPTIONS}
                    onChange={setNewColType}
                    className="w-full rounded border border-border bg-raised px-3 py-2 text-sm text-foreground"
                    menuClassName="text-sm"
                  />
                </div>
                {(newColType === "select" || newColType === "multiselect") && <div><label className="text-xs text-muted mb-1 block">Options (comma-separated)</label><input value={newColOptions} onChange={(e) => setNewColOptions(e.target.value)} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" placeholder="option1, option2" /></div>}
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowAddCol(false)} className="text-sm text-muted hover:text-foreground px-3 py-1.5">Cancel</button>
                <button onClick={handleAddColumn} className="text-sm bg-[var(--color-brand-600)] hover:bg-[var(--color-brand-700)] text-white px-4 py-1.5 rounded">Add</button>
              </div>
            </div>
          </div>
        )}

        {/* Row detail modal */}
        {detailRow && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setDetailRow(null)}>
            <div className="bg-surface border border-border rounded-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-bold font-display text-foreground">Row Detail</h2>
                <span className="text-[10px] font-mono text-muted">{detailRow.id.slice(0, 8)}</span>
              </div>
              <div className="space-y-3">
                {sortedColumns.map((col) => (
                  <div key={col.id}>
                    <label className="text-xs text-muted mb-1 block flex items-center gap-1.5">
                      <span className="text-[10px] font-mono text-muted/60">{TYPE_ICONS[col.type]}</span> {col.name}
                    </label>
                    {col.type === "boolean" ? (
                      <label className="flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={detailValues[col.id] === "true" || detailValues[col.id] === "1"} onChange={(e) => setDetailValues((prev) => ({ ...prev, [col.id]: String(e.target.checked) }))} className="accent-brand" /> {detailValues[col.id] === "true" ? "Yes" : "No"}</label>
                    ) : col.type === "select" && col.options ? (
                      <CustomSelect
                        value={detailValues[col.id] || ""}
                        options={[
                          { value: "", label: "--" },
                          ...col.options.map((o) => ({ value: o, label: o })),
                        ]}
                        onChange={(next) =>
                          setDetailValues((prev) => ({ ...prev, [col.id]: next }))
                        }
                        className="w-full rounded border border-border bg-raised px-3 py-2 text-sm text-foreground"
                        menuClassName="text-sm"
                      />
                    ) : (
                      <input type={col.type === "number" ? "number" : col.type === "date" ? "date" : col.type === "datetime" ? "datetime-local" : "text"} value={detailValues[col.id] || ""} onChange={(e) => setDetailValues((prev) => ({ ...prev, [col.id]: e.target.value }))} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" />
                    )}
                  </div>
                ))}
                {/* Metadata */}
                <div className="pt-3 border-t border-border space-y-1">
                  <div className="text-[10px] text-muted font-mono">Created: {new Date(detailRow.created_at).toLocaleString()}</div>
                  <div className="text-[10px] text-muted font-mono">Updated: {new Date(detailRow.updated_at).toLocaleString()}</div>
                  <div className="text-[10px] text-muted font-mono">Created by: {detailRow.created_by.slice(0, 8)}</div>
                </div>
              </div>
              <div className="flex justify-between mt-5">
                <button onClick={() => { handleDuplicateRow(detailRow.id); setDetailRow(null); }} className="text-sm text-muted hover:text-foreground px-3 py-1.5">Duplicate</button>
                <div className="flex gap-2">
                  <button onClick={() => setDetailRow(null)} className="text-sm text-muted hover:text-foreground px-3 py-1.5">Cancel</button>
                  <button onClick={saveDetail} className="text-sm bg-[var(--color-brand-600)] hover:bg-[var(--color-brand-700)] text-white px-4 py-1.5 rounded">Save</button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
  );

  // Anonymous stash viewers don't have a workspace context to power the
  // sidebar, so they get the bare table. Signed-in users see the full
  // AppShell either way.
  if (!user) {
    return <main className="flex min-h-screen flex-col bg-background">{tableContent}</main>;
  }
  return (
    <AppShell user={user} onLogout={logout}>
      {tableContent}
    </AppShell>
  );
}

function TableGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M3 16h18M9 4v16M15 4v16" />
    </svg>
  );
}
