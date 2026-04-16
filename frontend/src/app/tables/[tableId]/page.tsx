"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  getTable, updateTable,
  deleteTable, addTableColumn, updateTableColumn,
  deleteTableColumn, reorderTableColumns, listTableRows, searchTableRows,
  createTableRow, createTableRowsBatch, updateTableRow, deleteTableRow,
  deleteTableRowsBatch, duplicateTableRow, summarizeTableRows,
  listAllTables, saveTableView, deleteTableView,
  setTableEmbeddingConfig, backfillTableEmbeddings,
} from "../../../lib/api";
import type { Table, TableColumn, TableRow, TableView } from "../../../lib/types";

// --- Constants ---
const TYPE_ICONS: Record<string, string> = {
  text: "Aa", number: "#", boolean: "\u2713", date: "\uD83D\uDCC5", datetime: "\uD83D\uDD53",
  url: "\uD83D\uDD17", email: "@", select: "\u25BC", multiselect: "\u2261", json: "{}",
};
const COLUMN_TYPES = ["text", "number", "boolean", "date", "datetime", "url", "email", "select", "multiselect", "json"] as const;
const PAGE_SIZE = 100;
const FILTER_OPS = ["eq", "neq", "gt", "gte", "lt", "lte", "contains", "is_empty", "is_not_empty"] as const;

interface FilterDef { column_id: string; op: string; value: string }
type SummaryData = { total_rows: number; columns: Record<string, { name: string; filled: number; sum?: number; avg?: number; min?: number; max?: number }> };

export default function TableEditorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tableId = params.tableId as string;
  const urlWorkspaceId = searchParams.get("workspaceId");
  const { user, loading, logout } = useAuth();

  // Core state
  const [resolvedWorkspaceId, setResolvedWorkspaceId] = useState<string | null>(urlWorkspaceId);
  const [table, setTable] = useState<Table | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [error, setError] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");

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

  // Views
  const [activeViewId, setActiveViewId] = useState<string | null>(null);

  // Embeddings
  const [showEmbeddings, setShowEmbeddings] = useState(false);
  const [embeddingCols, setEmbeddingCols] = useState<Set<string>>(new Set());
  const [embeddingEnabled, setEmbeddingEnabled] = useState(false);
  const [backfillStatus, setBackfillStatus] = useState("");

  // CSV import
  const fileInputRef = useRef<HTMLInputElement>(null);

  const wsId = resolvedWorkspaceId;
  const sortedColumns = table?.columns ? [...table.columns].sort((a, b) => a.order - b.order) : [];
  const visibleColumns = sortedColumns.filter((c) => !hiddenCols.has(c.id));
  const hasMore = offset < totalCount;

  // --- Data Loading ---
  const loadTable = useCallback(async () => {
    try {
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
  }, [tableId, resolvedWorkspaceId]);

  const buildRowParams = useCallback((pageOffset: number) => {
    const p: { sort_by?: string; sort_order?: string; limit?: number; offset?: number; filters?: object[] } = {
      limit: PAGE_SIZE, offset: pageOffset,
    };
    if (sortBy) { p.sort_by = sortBy; p.sort_order = sortOrder; }
    if (filters.length > 0) p.filters = filters;
    return p;
  }, [sortBy, sortOrder, filters]);

  const loadRows = useCallback(async () => {
    try {
      if (searchQuery) {
        const res = await searchTableRows(wsId, tableId, searchQuery, { limit: PAGE_SIZE, offset: 0 });
        setRows(res?.rows ?? []); setTotalCount(res?.total_count ?? 0); setOffset(res?.rows?.length ?? 0);
      } else {
        const res = await listTableRows(wsId, tableId, buildRowParams(0));
        setRows(res?.rows ?? []); setTotalCount(res?.total_count ?? 0); setOffset(res?.rows?.length ?? 0);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
  }, [tableId, wsId, buildRowParams, searchQuery]);

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const res = searchQuery
        ? await searchTableRows(wsId, tableId, searchQuery, { limit: PAGE_SIZE, offset })
        : await listTableRows(wsId, tableId, buildRowParams(offset));
      const newRows = res?.rows ?? [];
      setRows((prev) => [...prev, ...newRows]);
      setOffset((prev) => prev + newRows.length);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
    setLoadingMore(false);
  }, [tableId, wsId, offset, loadingMore, hasMore, buildRowParams, searchQuery]);

  const loadSummary = useCallback(async () => {
    if (!showSummary) return;
    try {
      const s = await summarizeTableRows(wsId, tableId, filters.length > 0 ? filters : undefined);
      setSummary(s);
    } catch { /* ignore */ }
  }, [tableId, wsId, filters, showSummary]);

  useEffect(() => { if (user) loadTable(); }, [user, loadTable]);
  useEffect(() => { if (user && table) loadRows(); }, [user, table, loadRows]);
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
    const handler = () => setColMenu(null);
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

  // --- Filter ---
  const addFilter = () => {
    if (sortedColumns.length === 0) return;
    setFilters((prev) => [...prev, { column_id: sortedColumns[0].id, op: "eq", value: "" }]);
    setShowFilterBar(true);
  };
  const updateFilter = (idx: number, field: keyof FilterDef, val: string) => setFilters((prev) => prev.map((f, i) => (i === idx ? { ...f, [field]: val } : f)));
  const removeFilter = (idx: number) => setFilters((prev) => prev.filter((_, i) => i !== idx));

  // --- Table ops ---
  const handleRename = async () => {
    if (!table || !nameInput.trim()) return;
    try {
      const updated = await updateTable(resolvedWorkspaceId, tableId, { name: nameInput.trim() });
      setTable(updated); setEditingName(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename"); }
  };
  const handleDelete = async () => {
    if (!confirm("Delete this table and all its data?")) return;
    try {
      await deleteTable(resolvedWorkspaceId, tableId);
      router.push("/tables");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  // --- Column ops ---
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
  const handleColumnDrop = async (targetColId: string) => {
    if (!dragCol || dragCol === targetColId) { setDragCol(null); return; }
    const ids = sortedColumns.map((c) => c.id);
    const fromIdx = ids.indexOf(dragCol);
    const toIdx = ids.indexOf(targetColId);
    if (fromIdx === -1 || toIdx === -1) { setDragCol(null); return; }
    ids.splice(fromIdx, 1); ids.splice(toIdx, 0, dragCol); setDragCol(null);
    try { setTable(await reorderTableColumns(wsId, tableId, ids)); } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- Row ops ---
  const handleAddRow = async () => {
    try { const row = await createTableRow(wsId, tableId, {}); setRows((prev) => [...prev, row]); setTotalCount((c) => c + 1); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to add row"); }
  };
  const handleDeleteRow = async (rowId: string) => {
    try { await deleteTableRow(wsId, tableId, rowId); setRows((prev) => prev.filter((r) => r.id !== rowId)); setTotalCount((c) => c - 1); setSelectedRows((prev) => { const n = new Set(prev); n.delete(rowId); return n; }); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleDuplicateRow = async (rowId: string) => {
    try { const row = await duplicateTableRow(wsId, tableId, rowId); setRows((prev) => [...prev, row]); setTotalCount((c) => c + 1); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to duplicate"); }
  };
  const handleBulkDelete = async () => {
    if (selectedRows.size === 0 || !confirm(`Delete ${selectedRows.size} rows?`)) return;
    try { await deleteTableRowsBatch(wsId, tableId, Array.from(selectedRows)); setRows((prev) => prev.filter((r) => !selectedRows.has(r.id))); setTotalCount((c) => c - selectedRows.size); setSelectedRows(new Set()); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- Cell editing ---
  const startEditing = (rowId: string, colId: string, currentValue: unknown) => {
    setEditingCell({ rowId, colId }); setCellValue(currentValue != null ? String(currentValue) : "");
  };
  const commitEdit = async () => {
    if (!editingCell) return;
    const { rowId, colId } = editingCell;
    const col = sortedColumns.find((c) => c.id === colId);
    let typedValue: unknown = cellValue;
    if (col) {
      if (col.type === "number") typedValue = cellValue === "" ? null : Number(cellValue);
      else if (col.type === "boolean") typedValue = cellValue === "true" || cellValue === "1";
    }
    try { const updated = await updateTableRow(wsId, tableId, rowId, { [colId]: typedValue }); setRows((prev) => prev.map((r) => (r.id === rowId ? updated : r))); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
    setEditingCell(null);
  };
  const cancelEdit = () => setEditingCell(null);

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
    try { const updated = await updateTableRow(wsId, tableId, detailRow.id, data); setRows((prev) => prev.map((r) => (r.id === detailRow.id ? updated : r))); setDetailRow(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- Views ---
  const handleSaveView = async () => {
    const name = prompt("View name:");
    if (!name) return;
    try {
      const view = { name, filters: filters.length > 0 ? filters : undefined, sort_by: sortBy || undefined, sort_order: sortBy ? sortOrder : undefined, visible_columns: hiddenCols.size > 0 ? visibleColumns.map((c) => c.id) : undefined };
      const updated = await saveTableView(wsId, tableId, view);
      setTable(updated);
      const saved = updated.views?.find((v: TableView) => v.name === name);
      if (saved) setActiveViewId(saved.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  const handleLoadView = (view: TableView) => {
    setActiveViewId(view.id);
    setFilters(view.filters?.map((f) => ({ column_id: f.column_id, op: f.op, value: f.value || "" })) ?? []);
    setSortBy(view.sort_by || ""); setSortOrder((view.sort_order as "asc" | "desc") || "asc");
    if (view.visible_columns) { const vis = new Set(view.visible_columns); setHiddenCols(new Set(sortedColumns.filter((c) => !vis.has(c.id)).map((c) => c.id))); } else { setHiddenCols(new Set()); }
    if (view.filters && view.filters.length > 0) setShowFilterBar(true); else setShowFilterBar(false);
  };
  const handleDeleteView = async (viewId: string) => {
    try { const updated = await deleteTableView(wsId, tableId, viewId); setTable(updated); if (activeViewId === viewId) { setActiveViewId(null); setFilters([]); setSortBy(""); setSortOrder("asc"); setShowFilterBar(false); setHiddenCols(new Set()); } }
    catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  // --- CSV ---
  const handleCsvImport = async (file: File) => {
    try {
      const text = await file.text();
      const lines = text.split("\n").filter((l) => l.trim());
      if (lines.length < 2) { setError("CSV needs header + data"); return; }
      const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
      const existingNames = new Set(sortedColumns.map((c) => c.name));
      let currentTable = table!;
      for (const h of headers) { if (!existingNames.has(h)) currentTable = await addTableColumn(wsId, tableId, { name: h, type: "text" }); }
      setTable(currentTable);
      const colMap: Record<string, string> = {}; for (const col of currentTable.columns) colMap[col.name] = col.id;
      const rowsData: Record<string, unknown>[] = [];
      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].match(/(".*?"|[^,]+)/g)?.map((v) => v.trim().replace(/^"|"$/g, "")) || [];
        const data: Record<string, unknown> = {};
        headers.forEach((h, idx) => { if (colMap[h] && idx < values.length) data[colMap[h]] = values[idx]; });
        rowsData.push(data);
      }
      for (let i = 0; i < rowsData.length; i += 5000) { await createTableRowsBatch(wsId, tableId, rowsData.slice(i, i + 5000).map((d) => ({ data: d }))); }
      await loadRows(); await loadTable();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to import"); }
  };
  const handleCsvExport = () => {
    if (!table) return;
    const base = wsId ? `/api/v1/workspaces/${wsId}/tables` : "/api/v1/tables";
    const p = new URLSearchParams();
    if (sortBy) { p.set("sort_by", sortBy); p.set("sort_order", sortOrder); }
    if (filters.length > 0) p.set("filters", JSON.stringify(filters));
    const url = `${base}/${tableId}/export/csv${p.toString() ? "?" + p : ""}`;
    const token = localStorage.getItem("api_key") || "";
    fetch(url, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.blob()).then((blob) => {
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${table.name.replace(/\s+/g, "_")}.csv`; a.click(); URL.revokeObjectURL(a.href);
    }).catch(() => setError("Export failed"));
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

  useEffect(() => { if (!loading && !user) router.push("/login"); }, [user, loading, router]);
  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) return null;

  // --- Render row ---
  const renderRow = (row: TableRow, idx: number) => (
    <tr key={row.id} className={`border-b border-border/50 hover:bg-raised/50 transition-colors group ${selectedRows.has(row.id) ? "bg-brand/5" : ""}`}>
      <td className="px-1 py-0 text-center border-r border-border sticky left-0 z-[5] bg-surface"><input type="checkbox" checked={selectedRows.has(row.id)} onChange={() => toggleSelectRow(row.id)} className="accent-brand" /></td>
      <td className="px-2 py-1.5 text-[10px] text-muted text-center border-r border-border font-mono cursor-pointer hover:text-brand sticky left-8 z-[5] bg-surface shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]" onClick={() => openDetail(row)} title="Open row detail">{idx + 1}</td>
      {visibleColumns.map((col) => {
        const isEditing = editingCell?.rowId === row.id && editingCell?.colId === col.id;
        const value = row.data[col.id];
        const cellBg = showSummary ? getCellBg(col, value) : "";
        return (
          <td key={col.id} className={`px-1 py-0 border-r border-border/50 min-w-[140px] ${cellBg}`} onClick={() => { if (!isEditing) startEditing(row.id, col.id, value); }}>
            {isEditing ? (
              col.type === "boolean" ? (
                <label className="flex items-center h-8 px-2 cursor-pointer"><input type="checkbox" checked={cellValue === "true" || cellValue === "1"} onChange={(e) => setCellValue(String(e.target.checked))} onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }} className="accent-brand" autoFocus /></label>
              ) : col.type === "select" && col.options ? (
                <select value={cellValue} onChange={(e) => setCellValue(e.target.value)} onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); if (e.key === "Tab") { e.preventDefault(); commitEdit(); } }} className="w-full h-8 px-2 text-sm bg-transparent outline-none font-mono text-foreground" autoFocus>
                  <option value="">--</option>{col.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              ) : (
                <input ref={cellInputRef} type={col.type === "number" ? "number" : col.type === "date" ? "date" : col.type === "datetime" ? "datetime-local" : "text"} value={cellValue} onChange={(e) => setCellValue(e.target.value)} onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); if (e.key === "Tab") { e.preventDefault(); commitEdit(); } }} className="w-full h-8 px-2 text-sm bg-transparent outline-none ring-1 ring-brand rounded font-mono text-foreground" />
              )
            ) : (
              <div className={`${wrapCells ? "min-h-[32px] py-1" : "h-8"} px-2 flex items-center text-sm font-mono text-foreground ${wrapCells ? "whitespace-normal break-words" : "truncate"} cursor-text`}>
                {col.type === "boolean" ? <span className={value ? "text-green-400" : "text-muted"}>{value ? "\u2713" : "\u2717"}</span>
                : col.type === "url" && value ? <a href={String(value)} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline truncate" onClick={(e) => e.stopPropagation()}>{String(value)}</a>
                : <span className={value != null && value !== "" ? "" : "text-muted/30"}>{value != null && value !== "" ? String(value) : "\u2014"}</span>}
              </div>
            )}
          </td>
        );
      })}
      <td className="px-1 py-0" />
      <td className="px-1 py-0 whitespace-nowrap">
        <button onClick={() => handleDuplicateRow(row.id)} className="text-xs text-muted/50 hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity px-1" title="Duplicate">\u2398</button>
        <button onClick={() => handleDeleteRow(row.id)} className="text-xs text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1" title="Delete">&times;</button>
      </td>
    </tr>
  );

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Pages / Tables tab bar */}
        <div className="flex items-center gap-0 px-4 border-b border-border bg-surface flex-shrink-0">
          <button
            onClick={() => router.push("/notebooks?tab=pages")}
            className="px-4 py-2.5 text-sm font-medium transition-colors text-dim hover:text-foreground"
          >
            Pages
          </button>
          <button
            className="px-4 py-2.5 text-sm font-medium transition-colors relative text-brand"
          >
            Tables
            <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-brand rounded-t" />
          </button>
        </div>
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-surface flex-shrink-0 flex-wrap">
          <button onClick={() => router.push("/notebooks?tab=tables")} className="text-muted hover:text-foreground text-sm">&larr;</button>
          {editingName ? (
            <input value={nameInput} onChange={(e) => setNameInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setEditingName(false); }} onBlur={handleRename} className="text-lg font-bold font-display bg-transparent border-b border-brand outline-none text-foreground" autoFocus />
          ) : (
            <h1 onClick={() => { setEditingName(true); setNameInput(table?.name || ""); }} className="text-lg font-bold font-display text-foreground cursor-pointer hover:text-brand transition-colors">{table?.name || "Loading..."}</h1>
          )}
          {/* Search */}
          <div className="flex-1 max-w-xs">
            <input value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); setIsSearching(true); }} placeholder="Search all columns..." className="w-full px-3 py-1.5 text-xs bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" />
          </div>
          <div className="flex-1" />
          {table && <>
            <span className="text-[11px] font-mono text-muted">{visibleColumns.length}/{sortedColumns.length} cols</span>
            <span className="text-[11px] font-mono text-muted">{totalCount} rows</span>
            <button onClick={addFilter} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Filter</button>
            {(filters.length > 0 || sortBy) && <button onClick={handleSaveView} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Save view</button>}
            {/* Group by */}
            <select value={groupByCol} onChange={(e) => { setGroupByCol(e.target.value); setCollapsedGroups(new Set()); }} className="text-xs bg-raised border border-border rounded px-2 py-1 text-foreground outline-none">
              <option value="">No grouping</option>
              {sortedColumns.filter((c) => c.type === "select" || c.type === "text").map((c) => <option key={c.id} value={c.id}>Group: {c.name}</option>)}
            </select>
            <button onClick={() => setShowSummary((p) => !p)} className={`text-xs px-2 py-1 rounded ${showSummary ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>Summary</button>
            {wsId && <button onClick={() => setShowEmbeddings((p) => !p)} className={`text-xs px-2 py-1 rounded ${showEmbeddings ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>Embeddings</button>}
            <button onClick={() => setShowColVisibility((p) => !p)} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Columns</button>
            <button onClick={() => setWrapCells((p) => !p)} className={`text-xs px-2 py-1 rounded ${wrapCells ? "bg-brand/15 text-brand" : "text-muted hover:text-foreground hover:bg-raised"}`}>{wrapCells ? "Wrap" : "Compact"}</button>
            <button onClick={handleCsvExport} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Export</button>
            <button onClick={() => fileInputRef.current?.click()} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised">Import</button>
            <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { if (e.target.files?.[0]) handleCsvImport(e.target.files[0]); e.target.value = ""; }} />
            {selectedRows.size > 0 && <button onClick={handleBulkDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete {selectedRows.size}</button>}
            <button onClick={handleDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">Delete table</button>
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
                className="text-xs bg-brand hover:bg-brand-hover text-foreground px-2 py-1 rounded"
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

        {/* View tabs */}
        {table?.views && table.views.length > 0 && (
          <div className="px-4 py-1.5 border-b border-border bg-surface flex items-center gap-1 flex-shrink-0 overflow-x-auto">
            <button onClick={() => { setActiveViewId(null); setFilters([]); setSortBy(""); setSortOrder("asc"); setShowFilterBar(false); setHiddenCols(new Set()); }} className={`px-3 py-1 text-xs rounded ${!activeViewId ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}>All rows</button>
            {table.views.map((view: TableView) => (
              <div key={view.id} className="flex items-center group">
                <button onClick={() => handleLoadView(view)} className={`px-3 py-1 text-xs rounded ${activeViewId === view.id ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}>{view.name}</button>
                <button onClick={() => handleDeleteView(view.id)} className="text-[10px] text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 -ml-1">&times;</button>
              </div>
            ))}
            <button onClick={handleSaveView} className="px-2 py-1 text-xs text-muted hover:text-brand">+ Save view</button>
          </div>
        )}

        {/* Filter bar */}
        {showFilterBar && filters.length > 0 && (
          <div className="px-4 py-2 border-b border-border bg-raised/50 flex flex-wrap items-center gap-2 flex-shrink-0">
            {filters.map((f, idx) => (
              <div key={idx} className="flex items-center gap-1 bg-surface border border-border rounded px-2 py-1 text-xs">
                <select value={f.column_id} onChange={(e) => updateFilter(idx, "column_id", e.target.value)} className="bg-transparent outline-none text-foreground">
                  {sortedColumns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <select value={f.op} onChange={(e) => updateFilter(idx, "op", e.target.value)} className="bg-transparent outline-none text-muted">
                  {FILTER_OPS.map((op) => <option key={op} value={op}>{op}</option>)}
                </select>
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
                    <th key={col.id} className={`px-3 py-2 text-left text-xs font-medium text-muted border-r border-border min-w-[140px] select-none cursor-pointer hover:bg-raised transition-colors ${dragCol === col.id ? "opacity-50" : ""}`} draggable onDragStart={() => setDragCol(col.id)} onDragOver={(e) => e.preventDefault()} onDrop={() => handleColumnDrop(col.id)} onDragEnd={() => setDragCol(null)} onContextMenu={(e) => { e.preventDefault(); setColMenu({ colId: col.id, x: e.clientX, y: e.clientY }); }}>
                      <span className="flex items-center gap-1.5" onClick={() => handleSort(col.id)}>
                        <span className="text-[10px] text-muted/60 font-mono">{TYPE_ICONS[col.type] || "?"}</span>
                        {col.name}
                        {sortBy === col.id && <span className="text-brand text-[10px]">{sortOrder === "asc" ? "\u25B2" : "\u25BC"}</span>}
                      </span>
                    </th>
                  ))}
                  <th className="w-10 px-2 py-2 border-r border-border"><button onClick={() => setShowAddCol(true)} className="w-6 h-6 rounded bg-raised hover:bg-brand/15 text-muted hover:text-brand text-sm font-bold">+</button></th>
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
                  rows.map((row, idx) => renderRow(row, idx))
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
            <button onClick={handleAddRow} className="w-full py-2 text-sm text-muted hover:text-foreground hover:bg-raised border-b border-border/50 transition-colors text-left px-4">+ New row</button>
            {hasMore && <div ref={sentinelRef} className="py-4 text-center text-xs text-muted">{loadingMore ? "Loading..." : `${totalCount - offset} more rows`}</div>}
          </div>
        )}

        {/* Column context menu */}
        {colMenu && (
          <div className="fixed z-50 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[160px]" style={{ left: colMenu.x, top: colMenu.y }} onClick={(e) => e.stopPropagation()}>
            <button onClick={() => { handleSort(colMenu.colId); setColMenu(null); }} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Sort {sortBy === colMenu.colId && sortOrder === "asc" ? "descending" : "ascending"}</button>
            <button onClick={() => handleRenameColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Rename</button>
            <button onClick={() => { setHiddenCols((prev) => new Set([...prev, colMenu.colId])); setColMenu(null); }} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised">Hide column</button>
            <button onClick={() => handleDeleteColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-red-400 hover:bg-raised">Delete column</button>
          </div>
        )}

        {/* Add column dialog */}
        {showAddCol && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddCol(false)}>
            <div className="bg-surface border border-border rounded-xl p-6 w-[360px] shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-base font-bold font-display text-foreground mb-4">Add Column</h2>
              <div className="space-y-3">
                <div><label className="text-xs text-muted mb-1 block">Name</label><input value={newColName} onChange={(e) => setNewColName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleAddColumn(); }} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" autoFocus placeholder="Column name" /></div>
                <div><label className="text-xs text-muted mb-1 block">Type</label><select value={newColType} onChange={(e) => setNewColType(e.target.value)} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none">{COLUMN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
                {(newColType === "select" || newColType === "multiselect") && <div><label className="text-xs text-muted mb-1 block">Options (comma-separated)</label><input value={newColOptions} onChange={(e) => setNewColOptions(e.target.value)} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" placeholder="option1, option2" /></div>}
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowAddCol(false)} className="text-sm text-muted hover:text-foreground px-3 py-1.5">Cancel</button>
                <button onClick={handleAddColumn} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded">Add</button>
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
                      <select value={detailValues[col.id] || ""} onChange={(e) => setDetailValues((prev) => ({ ...prev, [col.id]: e.target.value }))} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none">
                        <option value="">--</option>{col.options.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
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
                  <button onClick={saveDetail} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded">Save</button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
