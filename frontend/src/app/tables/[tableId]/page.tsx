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
  listTableRows,
  createTableRow,
  updateTableRow,
  deleteTableRow,
  listAllTables,
} from "../../../lib/api";
import type { Table, TableColumn, TableRow } from "../../../lib/types";

// --- Column type icons ---
const TYPE_ICONS: Record<string, string> = {
  text: "Aa",
  number: "#",
  boolean: "\u2713",
  date: "\uD83D\uDCC5",
  datetime: "\uD83D\uDD53",
  url: "\uD83D\uDD17",
  email: "@",
  select: "\u25BC",
  multiselect: "\u2261",
  json: "{}",
};

const COLUMN_TYPES = [
  "text", "number", "boolean", "date", "datetime", "url", "email", "select", "multiselect", "json",
] as const;

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

  // Cell editing state
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

  const wsId = resolvedWorkspaceId || undefined;

  const loadTable = useCallback(async () => {
    try {
      if (resolvedWorkspaceId) {
        const t = await getTable(resolvedWorkspaceId, tableId);
        setTable(t);
      } else {
        try {
          const t = await getPersonalTable(tableId);
          setTable(t);
        } catch {
          const all = await listAllTables();
          const match = all?.tables?.find((t) => t.id === tableId);
          if (match && match.workspace_id) {
            setResolvedWorkspaceId(match.workspace_id);
            const t = await getTable(match.workspace_id, tableId);
            setTable(t);
          } else {
            setError("Table not found");
          }
        }
      }
    } catch { setError("Table not found"); }
  }, [tableId, resolvedWorkspaceId]);

  const loadRows = useCallback(async () => {
    try {
      const res = await listTableRows(tableId, { limit: 500 }, wsId);
      setRows(res?.rows ?? []);
      setTotalCount(res?.total_count ?? 0);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load rows"); }
  }, [tableId, wsId]);

  useEffect(() => { if (user) { loadTable(); loadRows(); } }, [user, loadTable, loadRows]);

  // Focus cell input when editing starts
  useEffect(() => {
    if (editingCell && cellInputRef.current) {
      cellInputRef.current.focus();
      cellInputRef.current.select();
    }
  }, [editingCell]);

  // Close column menu on outside click
  useEffect(() => {
    if (!colMenu) return;
    const handler = () => setColMenu(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [colMenu]);

  const sortedColumns = table?.columns
    ? [...table.columns].sort((a, b) => a.order - b.order)
    : [];

  // --- Handlers ---

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

  const handleAddColumn = async () => {
    if (!newColName.trim()) return;
    try {
      const col: { name: string; type: string; options?: string[] } = {
        name: newColName.trim(), type: newColType,
      };
      if ((newColType === "select" || newColType === "multiselect") && newColOptions.trim()) {
        col.options = newColOptions.split(",").map((o) => o.trim()).filter(Boolean);
      }
      const updated = await addTableColumn(tableId, col, wsId);
      setTable(updated);
      setShowAddCol(false);
      setNewColName("");
      setNewColType("text");
      setNewColOptions("");
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to add column"); }
  };

  const handleDeleteColumn = async (colId: string) => {
    if (!confirm("Delete this column? Data in this column will be hidden.")) return;
    try {
      const updated = await deleteTableColumn(tableId, colId, wsId);
      setTable(updated);
      setColMenu(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete column"); }
  };

  const handleRenameColumn = async (colId: string) => {
    const col = sortedColumns.find((c) => c.id === colId);
    if (!col) return;
    const name = prompt("Column name:", col.name);
    if (!name || name === col.name) return;
    try {
      const updated = await updateTableColumn(tableId, colId, { name }, wsId);
      setTable(updated);
      setColMenu(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to rename column"); }
  };

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
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to delete row"); }
  };

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
            </>
          )}
          <button onClick={handleDelete} className="text-xs text-red-400 hover:text-red-300 px-2 py-1">
            Delete
          </button>
        </div>
        {error && <p className="text-red-400 text-sm px-4 py-2">{error}</p>}

        {/* Grid */}
        {table && (
          <div className="flex-1 overflow-auto">
            <table className="w-full border-collapse min-w-max">
              <thead className="sticky top-0 z-10">
                <tr className="bg-surface border-b border-border">
                  <th className="w-10 px-2 py-2 text-[10px] font-medium text-muted text-center border-r border-border">#</th>
                  {sortedColumns.map((col) => (
                    <th
                      key={col.id}
                      className="px-3 py-2 text-left text-xs font-medium text-muted border-r border-border min-w-[140px] select-none cursor-pointer hover:bg-raised transition-colors"
                      onContextMenu={(e) => { e.preventDefault(); setColMenu({ colId: col.id, x: e.clientX, y: e.clientY }); }}
                      onClick={(e) => { setColMenu({ colId: col.id, x: e.clientX, y: e.clientY }); }}
                    >
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted/60 font-mono">{TYPE_ICONS[col.type] || "?"}</span>
                        {col.name}
                      </span>
                    </th>
                  ))}
                  <th className="w-10 px-2 py-2 border-r border-border">
                    <button
                      onClick={() => setShowAddCol(true)}
                      className="w-6 h-6 rounded bg-raised hover:bg-brand/15 text-muted hover:text-brand text-sm font-bold transition-colors"
                      title="Add column"
                    >
                      +
                    </button>
                  </th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={row.id} className="border-b border-border/50 hover:bg-raised/50 transition-colors group">
                    <td className="px-2 py-1.5 text-[10px] text-muted text-center border-r border-border font-mono">
                      {idx + 1}
                    </td>
                    {sortedColumns.map((col) => {
                      const isEditing = editingCell?.rowId === row.id && editingCell?.colId === col.id;
                      const value = row.data[col.id];
                      return (
                        <td
                          key={col.id}
                          className="px-1 py-0 border-r border-border/50 min-w-[140px]"
                          onClick={() => { if (!isEditing) startEditing(row.id, col.id, value); }}
                        >
                          {isEditing ? (
                            col.type === "boolean" ? (
                              <label className="flex items-center h-8 px-2 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={cellValue === "true" || cellValue === "1"}
                                  onChange={(e) => { setCellValue(String(e.target.checked)); }}
                                  onBlur={commitEdit}
                                  onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") cancelEdit(); }}
                                  ref={cellInputRef as unknown as React.Ref<HTMLInputElement>}
                                  className="accent-brand"
                                  autoFocus
                                />
                              </label>
                            ) : col.type === "select" && col.options ? (
                              <select
                                value={cellValue}
                                onChange={(e) => { setCellValue(e.target.value); }}
                                onBlur={commitEdit}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") commitEdit();
                                  if (e.key === "Escape") cancelEdit();
                                  if (e.key === "Tab") { e.preventDefault(); commitEdit(); }
                                }}
                                className="w-full h-8 px-2 text-sm bg-transparent outline-none font-mono text-foreground"
                                autoFocus
                              >
                                <option value="">--</option>
                                {col.options.map((opt) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            ) : (
                              <input
                                ref={cellInputRef}
                                type={col.type === "number" ? "number" : col.type === "date" ? "date" : col.type === "datetime" ? "datetime-local" : "text"}
                                value={cellValue}
                                onChange={(e) => setCellValue(e.target.value)}
                                onBlur={commitEdit}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") commitEdit();
                                  if (e.key === "Escape") cancelEdit();
                                  if (e.key === "Tab") { e.preventDefault(); commitEdit(); }
                                }}
                                className="w-full h-8 px-2 text-sm bg-transparent outline-none ring-1 ring-brand rounded font-mono text-foreground"
                              />
                            )
                          ) : (
                            <div className="h-8 px-2 flex items-center text-sm font-mono text-foreground truncate cursor-text">
                              {col.type === "boolean" ? (
                                <span className={value ? "text-green-400" : "text-muted"}>{value ? "\u2713" : "\u2717"}</span>
                              ) : col.type === "url" && value ? (
                                <a
                                  href={String(value)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-brand hover:underline truncate"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {String(value)}
                                </a>
                              ) : (
                                <span className={value != null && value !== "" ? "" : "text-muted/30"}>
                                  {value != null && value !== "" ? String(value) : "\u2014"}
                                </span>
                              )}
                            </div>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-1 py-0" />
                    <td className="px-1 py-0">
                      <button
                        onClick={() => handleDeleteRow(row.id)}
                        className="text-xs text-red-400/50 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity px-1"
                        title="Delete row"
                      >
                        &times;
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* Add row button */}
            <button
              onClick={handleAddRow}
              className="w-full py-2 text-sm text-muted hover:text-foreground hover:bg-raised border-b border-border/50 transition-colors text-left px-4"
            >
              + New row
            </button>
          </div>
        )}

        {/* Column context menu */}
        {colMenu && (
          <div
            className="fixed z-50 bg-surface border border-border rounded-lg shadow-lg py-1 min-w-[160px]"
            style={{ left: colMenu.x, top: colMenu.y }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => handleRenameColumn(colMenu.colId)}
              className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-raised transition-colors"
            >
              Rename
            </button>
            <button
              onClick={() => handleDeleteColumn(colMenu.colId)}
              className="w-full text-left px-3 py-1.5 text-sm text-red-400 hover:bg-raised transition-colors"
            >
              Delete column
            </button>
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
                  <input
                    value={newColName}
                    onChange={(e) => setNewColName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleAddColumn(); }}
                    className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand"
                    autoFocus
                    placeholder="Column name"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted mb-1 block">Type</label>
                  <select
                    value={newColType}
                    onChange={(e) => setNewColType(e.target.value)}
                    className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none"
                  >
                    {COLUMN_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                {(newColType === "select" || newColType === "multiselect") && (
                  <div>
                    <label className="text-xs text-muted mb-1 block">Options (comma-separated)</label>
                    <input
                      value={newColOptions}
                      onChange={(e) => setNewColOptions(e.target.value)}
                      className="w-full px-3 py-2 text-sm bg-raised border border-border rounded text-foreground outline-none focus:ring-1 focus:ring-brand"
                      placeholder="option1, option2, option3"
                    />
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowAddCol(false)} className="text-sm text-muted hover:text-foreground px-3 py-1.5">
                  Cancel
                </button>
                <button onClick={handleAddColumn} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-1.5 rounded">
                  Add
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
