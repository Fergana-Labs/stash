"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AppShell from "../../components/AppShell";
import { useAuth } from "../../hooks/useAuth";
import {
  listMyWorkspaces,
  listHistories,
  listNotebooks,
  listTables,
  searchHistoryEvents,
  semanticSearchPages,
  semanticSearchTableRows,
} from "../../lib/api";
import type {
  HistoryEvent,
  History,
  Notebook,
  NotebookPage,
  Table,
  TableRow,
  Workspace,
} from "../../lib/types";

interface SearchResults {
  historyEvents: { event: HistoryEvent; storeName: string }[];
  wikiPages: { page: NotebookPage; notebookName: string }[];
  tableRows: { row: TableRow; tableName: string; tableId: string }[];
}

const EMPTY_RESULTS: SearchResults = {
  historyEvents: [],
  wikiPages: [],
  tableRows: [],
};

export default function SearchPage() {
  const router = useRouter();
  const urlParams =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : null;
  const urlWs = urlParams?.get("ws") ?? null;
  const urlQ = urlParams?.get("q") ?? "";
  const { user, loading, logout } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWs, setSelectedWs] = useState<string>(urlWs || "");
  const [query, setQuery] = useState(urlQ);
  const [results, setResults] = useState<SearchResults>(EMPTY_RESULTS);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [autoSearchDone, setAutoSearchDone] = useState(false);

  const loadWorkspaces = useCallback(async () => {
    try {
      const res = await listMyWorkspaces();
      const ws = res?.workspaces ?? [];
      setWorkspaces(ws);
    } catch {}
  }, []);

  useEffect(() => {
    if (user) loadWorkspaces();
  }, [user, loadWorkspaces]);

  const handleSearch = useCallback(async () => {
    const q = query.trim();
    if (!q || !selectedWs) return;
    setSearching(true);
    setError("");
    setResults(EMPTY_RESULTS);
    setSearchedQuery(q);

    const historyEvents: SearchResults["historyEvents"] = [];
    const wikiPages: SearchResults["wikiPages"] = [];
    const tableRows: SearchResults["tableRows"] = [];

    try {
      // Discover resources in the workspace
      const [historiesRes, notebooksRes, tablesRes] = await Promise.all([
        listHistories(selectedWs).catch(() => ({ stores: [] as History[] })),
        listNotebooks(selectedWs).catch(() => ({ notebooks: [] as Notebook[] })),
        listTables(selectedWs).catch(() => ({ tables: [] as Table[] })),
      ]);

      const stores = historiesRes.stores ?? [];
      const notebooks = notebooksRes.notebooks ?? [];
      const tables = tablesRes.tables ?? [];

      // Search all resource types in parallel
      const searches = await Promise.allSettled([
        // History full-text search across all stores
        ...stores.map(async (store) => {
          const res = await searchHistoryEvents(selectedWs, store.id, q, 10);
          for (const event of res.events ?? []) {
            historyEvents.push({ event, storeName: store.name });
          }
        }),
        // Notebook semantic search across all notebooks
        ...notebooks.map(async (nb) => {
          const pages = await semanticSearchPages(selectedWs, nb.id, q, 10);
          for (const page of pages ?? []) {
            wikiPages.push({ page, notebookName: nb.name });
          }
        }),
        // Table semantic search across all tables
        ...tables.map(async (table) => {
          try {
            const rows = await semanticSearchTableRows(selectedWs, table.id, q, 10);
            for (const row of rows ?? []) {
              tableRows.push({ row, tableName: table.name, tableId: table.id });
            }
          } catch {
            // Table may not have embeddings enabled -- skip silently
          }
        }),
      ]);

      // Check if all searches failed
      const allFailed = searches.every((s) => s.status === "rejected");
      if (allFailed && searches.length > 0) {
        setError("All searches failed. Check that the workspace has accessible resources.");
      }

      setResults({ historyEvents, wikiPages, tableRows });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
    setSearching(false);
  }, [query, selectedWs]);

  // Auto-run the search once when the page is opened with ?q= and a workspace is ready.
  useEffect(() => {
    if (autoSearchDone) return;
    if (!urlQ) return;
    if (!selectedWs) return;
    setAutoSearchDone(true);
    handleSearch();
  }, [autoSearchDone, urlQ, selectedWs, handleSearch]);

  const totalResults =
    results.historyEvents.length +
    results.wikiPages.length +
    results.tableRows.length;

  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center text-muted">
        Loading...
      </div>
    );
  if (!user) {
    router.push("/login");
    return null;
  }

  return (
    <AppShell user={user} onLogout={logout}>
      <div className="max-w-3xl mx-auto w-full px-4 py-8">
        <h1 className="text-2xl font-bold text-foreground font-display mb-6">
          Search
        </h1>

        {/* Search Controls */}
        <div className="bg-surface border border-border rounded-lg p-4 mb-6">
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              placeholder="Search across history, notebooks, and tables..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && !e.shiftKey && handleSearch()
              }
              className="flex-1 text-sm bg-base border border-border rounded px-3 py-2.5 text-foreground placeholder:text-muted"
            />
            <button
              onClick={handleSearch}
              disabled={searching || !query.trim() || !selectedWs}
              className="text-sm bg-brand hover:bg-brand-hover text-foreground px-4 py-2.5 rounded disabled:opacity-50 whitespace-nowrap"
            >
              {searching ? "Searching..." : "Search"}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">Workspace:</span>
            <select
              value={selectedWs}
              onChange={(e) => setSelectedWs(e.target.value)}
              className="text-xs bg-base border border-border rounded px-2 py-1 text-foreground"
            >
              <option value="">Select a workspace</option>
              {workspaces.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name}
                </option>
              ))}
            </select>
            {!selectedWs && (
              <span className="text-xs text-muted">
                Select a workspace to search
              </span>
            )}
          </div>
        </div>

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        {/* Loading */}
        {searching && (
          <div className="text-center py-8">
            <div className="text-muted text-sm">
              Searching across history, notebooks, and tables...
            </div>
          </div>
        )}

        {/* Results */}
        {!searching && searchedQuery && (
          <div className="space-y-6">
            {totalResults === 0 && (
              <p className="text-sm text-muted text-center py-8">
                No results found for &ldquo;{searchedQuery}&rdquo;
              </p>
            )}

            {/* History Events */}
            {results.historyEvents.length > 0 && (
              <section>
                <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-mono">
                  History Events ({results.historyEvents.length})
                </h2>
                <div className="space-y-2">
                  {results.historyEvents.map(({ event, storeName }) => (
                    <div
                      key={event.id}
                      className="bg-surface border border-border rounded-lg px-4 py-3"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-400">
                          {event.agent_name}
                        </span>
                        <span className="text-xs text-muted font-mono">
                          {event.event_type}
                        </span>
                        <span className="text-xs text-muted ml-auto">
                          {new Date(event.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-sm text-foreground line-clamp-3">
                        {event.content}
                      </p>
                      <p className="text-xs text-muted mt-1">
                        Store: {storeName}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Wiki Pages */}
            {results.wikiPages.length > 0 && (
              <section>
                <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-mono">
                  Wiki Pages ({results.wikiPages.length})
                </h2>
                <div className="space-y-2">
                  {results.wikiPages.map(({ page, notebookName }) => (
                    <a
                      key={page.id}
                      href={`/notebooks?ws=${selectedWs}&nb=${page.notebook_id}&page=${page.id}`}
                      className="block bg-surface border border-border rounded-lg px-4 py-3 hover:border-brand/40 transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-foreground">
                          {page.name}
                        </span>
                        <span className="text-xs text-muted ml-auto">
                          {new Date(page.updated_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-sm text-muted line-clamp-2">
                        {page.content_markdown?.slice(0, 200)}
                      </p>
                      <p className="text-xs text-muted mt-1">
                        Notebook: {notebookName}
                      </p>
                    </a>
                  ))}
                </div>
              </section>
            )}

            {/* Table Rows */}
            {results.tableRows.length > 0 && (
              <section>
                <h2 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-mono">
                  Table Rows ({results.tableRows.length})
                </h2>
                <div className="space-y-2">
                  {results.tableRows.map(({ row, tableName, tableId }) => (
                    <a
                      key={row.id}
                      href={`/tables/${tableId}?ws=${selectedWs}`}
                      className="block bg-surface border border-border rounded-lg px-4 py-3 hover:border-brand/40 transition-colors"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-foreground">
                          {tableName}
                        </span>
                        <span className="text-xs text-muted ml-auto">
                          {new Date(row.updated_at).toLocaleDateString()}
                        </span>
                      </div>
                      <p className="text-sm text-muted line-clamp-2 font-mono">
                        {Object.entries(row.data)
                          .slice(0, 4)
                          .map(([k, v]) => `${k}: ${String(v)}`)
                          .join(" | ")}
                      </p>
                    </a>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
