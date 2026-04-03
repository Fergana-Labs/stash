"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "../../../components/AppShell";
import { useAuth } from "../../../hooks/useAuth";
import {
  getTable,
  getPersonalTable,
  updateTable,
  updatePersonalTable,
  deleteTable,
  deletePersonalTable,
  addTableColumn,
  updateTableColumn,
  deleteTableColumn,
  reorderTableColumns,
  listTableRows,
  createTableRow,
  createTableRowsBatch,
  updateTableRow,
  deleteTableRow,
  deleteTableRowsBatch,
  listAllTables,
  saveTableView,
  deleteTableView,
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

export default function TableEditorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const tableId = params.tableId as string;
  const urlWorkspaceId = searchParams.get("workspaceId");
  const { user, loading, logout } = useAuth();

  const [resolvedWorkspaceId, setResolvedWorkspaceId] = useState<string | null>(urlWorkspaceId);
  const [table, setTable] = useState<Table | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [error, setError] = useState("");
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");

  // Sort state
  const [sortBy, setSortBy] = useState<string>("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  // Filter state
  const [filters, setFilters] = useState<FilterDef[]>([]);
  const [showFilterBar, setShowFilterBar] = useState(false);

  // Pagination
  const [offset, setOffset] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  // Cell editing
  const [editingCell, setEditingCell] = useState<{ rowId: string; colId: string } | null>(null);
  const [cellValue, setCellValue] = useState<string>("");
  const cellInputRef = useRef<HTMLInputElement>(null);

  // Add column dialog
  const [showAddCol, setShowAddCol] = useState(false);
  const [newColName, setNewColName] = useState("");
  const [newColType, setNewColType] = useState<string>("text");
  const [newColOptions, setNewColOptions] = useState("");

  // Column context menu
  const [colMenu, setColMenu] = useState<{ colId: string; x: number; y: number } | null>(null);

  // Bulk selection
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());

  // CSV import
  const [showImport, setShowImport] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Column drag
  const [dragCol, setDragCol] = useState<string | null>(null);

  // Active view
  const [activeViewId, setActiveViewId] = useState<string | null>(null);

  const wsId = resolvedWorkspaceId || undefined;

  // --- Data Loading ---

  const loadTable = useCallback(async () => {
    try {
      if (resolvedWorkspaceId) {
        setTable(await getTable(resolvedWorkspaceId, tableId));
      } else {
        try {
          setTable(await getPersonalTable(tableId));
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
      const res = await listTableRows(tableId, buildRowParams(0), wsId);
      setRows(res?.rows ?? []);
      setTotalCount(res?.total_count ?? 0);
      setOffset(res?.rows?.length ?? 0);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
  }, [tableId, wsId, buildRowParams]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const res = await listTableRows(tableId, buildRowParams(offset), wsId);
      const newRows = res?.rows ?? [];
      setRows((prev) => [...prev, ...newRows]);
      setOffset((prev) => prev + newRows.length);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
    setLoadingMore(false);
  };

  useEffect(() => { if (user) loadTable(); }, [user, loadTable]);
  useEffect(() => { if (user && table) loadRows(); }, [user, table, loadRows]);

  useEffect(() => {
    if (editingCell && cellInputRef.current) { cellInputRef.current.focus(); cellInputRef.current.select(); }
  }, [editingCell]);

  useEffect(() => {
    if (!colMenu) return;
    const handler = () => setColMenu(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [colMenu]);

  const sortedColumns = table?.columns ? [...table.columns].sort((a, b) => a.order - b.order) : [];
  const hasMore = offset < totalCount;

  // --- Sort Handler ---
  const handleSort = (colId: string) => {
    if (sortBy === colId) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(colId);
      setSortOrder("asc");
    }
  };

  // --- Filter Handlers ---
  const addFilter = () => {
    if (sortedColumns.length === 0) return;
    setFilters((prev) => [...prev, { column_id: sortedColumns[0].id, op: "eq", value: "" }]);
    setShowFilterBar(true);
  };
  const updateFilter = (idx: number, field: keyof FilterDef, val: string) => {
    setFilters((prev) => prev.map((f, i) => (i === idx ? { ...f, [field]: val } : f)));
  };
  const removeFilter = (idx: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== idx));
  };

  // --- Table Name ---
  const handleRename = async () => {
    if (!table || !nameInput.trim()) return;
    try {
      const updated = resolvedWorkspaceId
        ? await updateTable(resolvedWorkspaceId, tableId, { name: nameInput.trim() })
        : await updatePersonalTable(tableId, { name: nameInput.trim() });
      setTable(updated);
      setEditingName(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename"); }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this table and all its data?")) return;
    try {
      if (resolvedWorkspaceId) await deleteTable(resolvedWorkspaceId, tableId);
      else await deletePersonalTable(tableId);
      router.push("/tables");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete"); }
  };

  // --- Column Handlers ---
  const handleAddColumn = async () => {
    if (!newColName.trim()) return;
    try {
      const col: { name: string; type: string; options?: string[] } = { name: newColName.trim(), type: newColType };
      if ((newColType === "select" || newColType === "multiselect") && newColOptions.trim()) {
        col.options = newColOptions.split(",").map((o) => o.trim()).filter(Boolean);
      }
      const updated = await addTableColumn(tableId, col, wsId);
      setTable(updated);
      setShowAddCol(false);
      setNewColName(""); setNewColType("text"); setNewColOptions("");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to add column"); }
  };

  const handleDeleteColumn = async (colId: string) => {
    if (!confirm("Delete this column?")) return;
    try { setTable(await deleteTableColumn(tableId, colId, wsId)); setColMenu(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to delete column"); }
  };

  const handleRenameColumn = async (colId: string) => {
    const col = sortedColumns.find((c) => c.id === colId);
    if (!col) return;
    const name = prompt("Column name:", col.name);
    if (!name || name === col.name) return;
    try { setTable(await updateTableColumn(tableId, colId, { name }, wsId)); setColMenu(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to rename column"); }
  };

  const handleColumnDrop = async (targetColId: string) => {
    if (!dragCol || dragCol === targetColId) { setDragCol(null); return; }
    const ids = sortedColumns.map((c) => c.id);
    const fromIdx = ids.indexOf(dragCol);
    const toIdx = ids.indexOf(targetColId);
    if (fromIdx === -1 || toIdx === -1) { setDragCol(null); return; }
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, dragCol);
    setDragCol(null);
    try { setTable(await reorderTableColumns(tableId, ids, wsId)); }
    catch (err) { setError(err instanceof Error ? err.message : "Failed to reorder"); }
  };

  // --- Row Handlers ---
  const handleAddRow = async () => {
    try {
      const row = await createTableRow(tableId, {}, wsId);
      setRows((prev) => [...prev, row]);
      setTotalCount((c) => c + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to add row"); }
  };

  const handleDeleteRow = async (rowId: string) => {
    try {
      await deleteTableRow(tableId, rowId, wsId);
      setRows((prev) => prev.filter((r) => r.id !== rowId));
      setTotalCount((c) => c - 1);
      setSelectedRows((prev) => { const n = new Set(prev); n.delete(rowId); return n; });
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete row"); }
  };

  const handleBulkDelete = async () => {
    if (selectedRows.size === 0) return;
    if (!confirm(`Delete ${selectedRows.size} rows?`)) return;
    try {
      await deleteTableRowsBatch(tableId, Array.from(selectedRows), wsId);
      setRows((prev) => prev.filter((r) => !selectedRows.has(r.id)));
      setTotalCount((c) => c - selectedRows.size);
      setSelectedRows(new Set());
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete rows"); }
  };

  // --- Cell Editing ---
  const startEditing = (rowId: string, colId: string, currentValue: unknown) => {
    setEditingCell({ rowId, colId });
    setCellValue(currentValue != null ? String(currentValue) : "");
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
    try {
      const updated = await updateTableRow(tableId, rowId, { [colId]: typedValue }, wsId);
      setRows((prev) => prev.map((r) => (r.id === rowId ? updated : r)));
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to update"); }
    setEditingCell(null);
  };

  const cancelEdit = () => setEditingCell(null);

  // --- CSV Import ---
  const handleCsvImport = async (file: File) => {
    setShowImport(false);
    try {
      const text = await file.text();
      const lines = text.split("\n").filter((l) => l.trim());
      if (lines.length < 2) { setError("CSV must have a header row and at least one data row"); return; }
      const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));

      // Auto-create columns that don't exist
      const existingNames = new Set(sortedColumns.map((c) => c.name));
      let currentTable = table!;
      for (const h of headers) {
        if (!existingNames.has(h)) {
          currentTable = await addTableColumn(tableId, { name: h, type: "text" }, wsId);
        }
      }
      setTable(currentTable);
      const colMap: Record<string, string> = {};
      for (const col of currentTable.columns) colMap[col.name] = col.id;

      // Parse rows
      const rowsData: Record<string, unknown>[] = [];
      for (let i = 1; i < lines.length; i++) {
        // Simple CSV parse (handles quoted fields with commas)
        const values = lines[i].match(/(".*?"|[^,]+)/g)?.map((v) => v.trim().replace(/^"|"$/g, "")) || [];
        const data: Record<string, unknown> = {};
        headers.forEach((h, idx) => {
          if (colMap[h] && idx < values.length) data[colMap[h]] = values[idx];
        });
        rowsData.push(data);
      }

      // Batch insert in chunks of 5000
      const chunkSize = 5000;
      for (let i = 0; i < rowsData.length; i += chunkSize) {
        const chunk = rowsData.slice(i, i + chunkSize).map((d) => ({ data: d }));
        await createTableRowsBatch(tableId, chunk, wsId);
      }

      await loadRows();
      await loadTable();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to import CSV"); }
  };

  // --- CSV Export ---
  const handleCsvExport = () => {
    if (!table || sortedColumns.length === 0) return;
    const base = wsId ? `/api/v1/workspaces/${wsId}/tables` : "/api/v1/tables";
    const params = new URLSearchParams();
    if (sortBy) { params.set("sort_by", sortBy); params.set("sort_order", sortOrder); }
    if (filters.length > 0) params.set("filters", JSON.stringify(filters));
    const qs = params.toString();
    // Trigger download by opening in new tab with auth
    const url = `${base}/${tableId}/export/csv${qs ? "?" + qs : ""}`;
    // Use fetch to add auth header then trigger download
    const token = typeof window !== "undefined" ? localStorage.getItem("api_key") || document.cookie.split("api_key=")[1]?.split(";")[0] : "";
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${table.name.replace(/\s+/g, "_")}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch(() => setError("Failed to export CSV"));
  };

  // --- Views ---
  const handleSaveView = async () => {
    const name = prompt("View name:");
    if (!name) return;
    try {
      const view = { name, filters: filters.length > 0 ? filters : undefined, sort_by: sortBy || undefined, sort_order: sortBy ? sortOrder : undefined };
      const updated = await saveTableView(tableId, view, wsId);
      setTable(updated);
      const saved = updated.views.find((v: TableView) => v.name === name);
      if (saved) setActiveViewId(saved.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to save view"); }
  };

  const handleLoadView = (view: TableView) => {
    setActiveViewId(view.id);
    setFilters(view.filters?.map((f) => ({ column_id: f.column_id, op: f.op, value: f.value || "" })) ?? []);
    setSortBy(view.sort_by || "");
    setSortOrder((view.sort_order as "asc" | "desc") || "asc");
    if (view.filters && view.filters.length > 0) setShowFilterBar(true);
  };

  const handleDeleteView = async (viewId: string) => {
    try {
      const updated = await deleteTableView(tableId, viewId, wsId);
      setTable(updated);
      if (activeViewId === viewId) {
        setActiveViewId(null);
        setFilters([]);
        setSortBy("");
        setSortOrder("asc");
        setShowFilterBar(false);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete view"); }
  };

  // --- Selection ---
  const toggleSelectAll = () => {
    if (selectedRows.size === rows.length) setSelectedRows(new Set());
    else setSelectedRows(new Set(rows.map((r) => r.id)));
  };
  const toggleSelectRow = (rowId: string) => {
    setSelectedRows((prev) => {
      const n = new Set(prev);
      if (n.has(rowId)) n.delete(rowId); else n.add(rowId);
      return n;
    });
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) { router.push("/login"); return null; }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-surface flex-shrink-0">
          <button onClick={() => router.push("/tables")} className="text-muted hover:text-foreground text-sm">&larr;</button>
          {editingName ? (
            <input
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") setEditingName(false); }}
              onBlur={handleRename}
              className="text-lg font-bold font-display bg-transparent border-b border-brand outline-none text-foreground"
              autoFocus
            />
          ) : (
            <h1
              onClick={() => { setEditingName(true); setNameInput(table?.name || ""); }}
              className="text-lg font-bold font-display text-foreground cursor-pointer hover:text-brand transition-colors"
            >
              {table?.name || "Loading..."}
            </h1>
          )}
          <div className="flex-1" />
          {table && (
            <>
              <span className="text-[11px] font-mono text-muted">{sortedColumns.length} cols</span>
              <span className="text-[11px] font-mono text-muted">{totalCount} rows</span>
              <button onClick={addFilter} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised" title="Add filter">
                Filter
              </button>
              {(filters.length > 0 || sortBy) && (
                <button onClick={handleSaveView} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised" title="Save current filters/sort as a view">
                  Save view
                </button>
              )}
              <button onClick={handleCsvExport} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised" title="Export CSV">
                Export
              </button>
              <button onClick={() => fileInputRef.current?.click()} className="text-xs text-muted hover:text-foreground px-2 py-1 rounded hover:bg-raised" title="Import CSV">
                Import
              </button>
              <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => { if (e.target.files?.[0]) handleCsvImport(e.target.files[0]); e.target.value = ""; }} />
              {selectedRows.size > 0 && (
                <button onClick={handleBulkDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">
                  Delete {selectedRows.size} rows
                </button>
              )}
              <button onClick={handleDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">
                Delete table
              </button>
            </>
          )}
        </div>

        {/* View tabs */}
        {table && table.views && table.views.length > 0 && (
          <div className="px-4 py-1.5 border-b border-border bg-surface flex items-center gap-1 flex-shrink-0 overflow-x-auto">
            <button
              onClick={() => { setActiveViewId(null); setFilters([]); setSortBy(""); setSortOrder("asc"); setShowFilterBar(false); }}
              className={`px-3 py-1 text-xs rounded transition-colors ${!activeViewId ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}
            >
              All rows
            </button>
            {table.views.map((view: TableView) => (
              <div key={view.id} className="flex items-center group">
                <button
                  onClick={() => handleLoadView(view)}
                  className={`px-3 py-1 text-xs rounded transition-colors ${activeViewId === view.id ? "bg-brand/15 text-brand font-medium" : "text-muted hover:text-foreground hover:bg-raised"}`}
                >
                  {view.name}
                </button>
                <button
                  onClick={() => handleDeleteView(view.id)}
                  className="text-[10px] text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity -ml-1"
                >
                  &times;
                </button>
              </div>
            ))}
            <button onClick={handleSaveView} className="px-2 py-1 text-xs text-muted hover:text-brand transition-colors" title="Save current view">
              + Save view
            </button>
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
                {f.op !== "is_empty" && f.op !== "is_not_empty" && (
                  <input
                    value={f.value}
                    onChange={(e) => updateFilter(idx, "value", e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") loadRows(); }}
                    className="w-24 bg-transparent outline-none text-foreground border-b border-border"
                    placeholder="value"
                  />
                )}
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
                  {/* Checkbox column */}
                  <th className="w-8 px-1 py-2 text-center border-r border-border">
                    <input type="checkbox" checked={selectedRows.size === rows.length && rows.length > 0} onChange={toggleSelectAll} className="accent-brand" />
                  </th>
                  <th className="w-10 px-2 py-2 text-[10px] font-medium text-muted text-center border-r border-border">#</th>
                  {sortedColumns.map((col) => (
                    <th
                      key={col.id}
                      className={`px-3 py-2 text-left text-xs font-medium text-muted border-r border-border min-w-[140px] select-none cursor-pointer hover:bg-raised transition-colors ${dragCol === col.id ? "opacity-50" : ""}`}
                      draggable
                      onDragStart={() => setDragCol(col.id)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => handleColumnDrop(col.id)}
                      onDragEnd={() => setDragCol(null)}
                      onContextMenu={(e) => { e.preventDefault(); setColMenu({ colId: col.id, x: e.clientX, y: e.clientY }); }}
                    >
                      <span className="flex items-center gap-1.5" onClick={() => handleSort(col.id)}>
                        <span className="text-[10px] text-muted/60 font-mono">{TYPE_ICONS[col.type] || "?"}</span>
                        {col.name}
                        {sortBy === col.id && (
                          <span className="text-brand text-[10px]">{sortOrder === "asc" ? "\u25B2" : "\u25BC"}</span>
                        )}
                      </span>
                    </th>
                  ))}
                  <th className="w-10 px-2 py-2 border-r border-border">
                    <button onClick={() => setShowAddCol(true)} className="w-6 h-6 rounded bg-raised hover:bg-brand/15 text-muted hover:text-brand text-sm font-bold transition-colors" title="Add column">+</button>
                  </th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={row.id} className={`border-b border-border/50 hover:bg-raised/50 transition-colors group ${selectedRows.has(row.id) ? "bg-brand/5" : ""}`}>
                    <td className="px-1 py-0 text-center border-r border-border">
                      <input type="checkbox" checked={selectedRows.has(row.id)} onChange={() => toggleSelectRow(row.id)} className="accent-brand" />
                    </td>
                    <td className="px-2 py-1.5 text-[10px] text-muted text-center border-r border-border font-mono">{idx + 1}</td>
                    {sortedColumns.map((col) => {
                      const isEditing = editingCell?.rowId === row.id && editingCell?.colId === col.id;
                      const value = row.data[col.id];
                      return (
                        <td key={col.id} className="px-1 py-0 border-r border-border/50 min-w-[140px]" onClick={() => { if (!isEditing) startEditing(row.id, col.id, value); }}>
                          {isEditing ? (
                            col.type === "boolean" ? (
                              <label className="flex items-center h-8 px-2 cursor-pointer">
                                <input type="checkbox" checked={cellValue === "true" || cellValue === "1"} onChange={(e) => setCellValue(String(e.target.checked))} onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }} className="accent-brand" autoFocus />
                              </label>
                            ) : col.type === "select" && col.options ? (
                              <select value={cellValue} onChange={(e) => setCellValue(e.target.value)} onBlur={commitEdit} onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); if (e.key === "Tab") { e.preventDefault(); commitEdit(); } }} className="w-full h-8 px-2 text-sm bg-transparent outline-none font-mono text-foreground" autoFocus>
                                <option value="">--</option>
                                {col.options.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                              </select>
                            ) : (
                              <input
                                ref={cellInputRef}
                                type={col.type === "number" ? "number" : col.type === "date" ? "date" : col.type === "datetime" ? "datetime-local" : "text"}
                                value={cellValue} onChange={(e) => setCellValue(e.target.value)} onBlur={commitEdit}
                                onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); if (e.key === "Tab") { e.preventDefault(); commitEdit(); } }}
                                className="w-full h-8 px-2 text-sm bg-transparent outline-none ring-1 ring-brand rounded font-mono text-foreground"
                              />
                            )
                          ) : (
                            <div className="h-8 px-2 flex items-center text-sm font-mono text-foreground truncate cursor-text">
                              {col.type === "boolean" ? (
                                <span className={value ? "text-green-400" : "text-muted"}>{value ? "\u2713" : "\u2717"}</span>
                              ) : col.type === "url" && value ? (
                                <a href={String(value)} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline truncate" onClick={(e) => e.stopPropagation()}>{String(value)}</a>
                              ) : (
                                <span className={value != null && value !== "" ? "" : "text-muted/30"}>{value != null && value !== "" ? String(value) : "\u2014"}</span>
                              )}
                            </div>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-1 py-0" />
                    <td className="px-1 py-0">
                      <button onClick={() => handleDeleteRow(row.id)} className="text-xs text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1" title="Delete row">&times;</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Load more / add row */}
            <div className="flex items-center border-b border-border/50">
              <button onClick={handleAddRow} className="flex-1 py-2 text-sm text-muted hover:text-foreground hover:bg-raised transition-colors text-left px-4">+ New row</button>
              {hasMore && (
                <button onClick={loadMore} disabled={loadingMore} className="px-4 py-2 text-sm text-brand hover:text-brand-hover transition-colors">
                  {loadingMore ? "Loading..." : `Load more (${totalCount - offset} remaining)`}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Column context menu */}
        {colMenu && (
          <div className="fixed z-50 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[160px]" style={{ left: colMenu.x, top: colMenu.y }} onClick={(e) => e.stopPropagation()}>
            <button onClick={() => { handleSort(colMenu.colId); setColMenu(null); }} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised transition-colors">
              Sort {sortBy === colMenu.colId && sortOrder === "asc" ? "descending" : "ascending"}
            </button>
            <button onClick={() => handleRenameColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised transition-colors">Rename</button>
            <button onClick={() => handleDeleteColumn(colMenu.colId)} className="w-full text-left px-3 py-1.5 text-sm text-red-400 hover:bg-raised transition-colors">Delete column</button>
          </div>
        )}

        {/* Add column dialog */}
        {showAddCol && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowAddCol(false)}>
            <div className="bg-surface border border-border rounded-xl p-6 w-[360px] shadow-xl" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-base font-bold font-display text-foreground mb-4">Add Column</h2>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-muted mb-1 block">Name</label>
                  <input value={newColName} onChange={(e) => setNewColName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleAddColumn(); }} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" autoFocus placeholder="Column name" />
                </div>
                <div>
                  <label className="text-xs text-muted mb-1 block">Type</label>
                  <select value={newColType} onChange={(e) => setNewColType(e.target.value)} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none">
                    {COLUMN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                {(newColType === "select" || newColType === "multiselect") && (
                  <div>
                    <label className="text-xs text-muted mb-1 block">Options (comma-separated)</label>
                    <input value={newColOptions} onChange={(e) => setNewColOptions(e.target.value)} className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand" placeholder="option1, option2, option3" />
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowAddCol(false)} className="text-sm text-muted hover:text-foreground px-3 py-1.5">Cancel</button>
                <button onClick={handleAddColumn} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded">Add</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
