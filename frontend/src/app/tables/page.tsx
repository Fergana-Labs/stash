"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import { listAllTables, listTables, createTable, deleteTable } from "../../lib/api";
import { Table, TableWithWorkspace } from "../../lib/types";

export default function TablesPage() {
  const router = useRouter();
  const wsId = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("ws") : null;
  const { user, loading, logout } = useAuth();
  const [tables, setTables] = useState<TableWithWorkspace[]>([]);
  const [error, setError] = useState("");

  const loadTables = useCallback(async () => {
    try {
      if (wsId) {
        const res = await listTables(wsId);
        const tbls = (res?.tables ?? []).map((t: Table) => ({ ...t, workspace_id: wsId, workspace_name: "" }));
        setTables(tbls);
      } else {
        const res = await listAllTables();
        setTables(res?.tables ?? []);
      }
    } catch { /* ignore */ }
  }, [wsId]);

  useEffect(() => { if (user) loadTables(); }, [user, loadTables]);

  const handleCreate = async () => {
    const name = prompt("Table name:");
    if (!name) return;
    try {
      const table = await createTable(null, name);
      router.push(`/tables/${table.id}`);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to create table"); }
  };

  useEffect(() => { if (!loading && !user) router.push("/login"); }, [user, loading, router]);
  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted">Loading...</div>;
  if (!user) return null;

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-foreground font-display">Tables</h1>
          <button onClick={handleCreate} className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded">
            New Table
          </button>
        </div>
        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}
        {tables.length === 0 ? (
          <p className="text-muted text-sm">No tables yet. Create one to get started — structured data that agents and humans can read and write.</p>
        ) : (
          <div className="space-y-1">
            {tables.map((table) => (
              <Link
                key={table.id}
                href={`/tables/${table.id}${table.workspace_id ? `?workspaceId=${table.workspace_id}` : ""}`}
                className="group flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-raised transition-colors"
              >
                <div className="w-7 h-7 rounded-md bg-cyan-500/15 text-cyan-500 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  T
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-foreground truncate">{table.name}</div>
                  {table.description && <div className="text-xs text-muted truncate">{table.description}</div>}
                </div>
                <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded font-mono flex-shrink-0">
                  {table.columns.length} cols
                </span>
                <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded font-mono flex-shrink-0">
                  {table.row_count ?? 0} rows
                </span>
                <span className="text-xs text-muted flex-shrink-0">
                  {new Date(table.updated_at).toLocaleDateString()}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
