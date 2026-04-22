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

type Tab = "all" | "history" | "notebooks" | "tables";

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "history", label: "History" },
  { id: "notebooks", label: "Notebooks" },
  { id: "tables", label: "Tables" },
];

const WS_STORAGE_KEY = "stash_selected_workspace";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

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
  const [tab, setTab] = useState<Tab>("all");
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
      if (!urlWs && ws.length > 0 && !selectedWs) {
        const saved =
          typeof window !== "undefined"
            ? localStorage.getItem(WS_STORAGE_KEY)
            : null;
        if (saved && ws.some((w) => w.id === saved)) {
          setSelectedWs(saved);
        } else {
          setSelectedWs(ws[0].id);
        }
      }
    } catch {}
  }, [urlWs, selectedWs]);

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
      const [historiesRes, notebooksRes, tablesRes] = await Promise.all([
        listHistories(selectedWs).catch(() => ({ stores: [] as History[] })),
        listNotebooks(selectedWs).catch(() => ({ notebooks: [] as Notebook[] })),
        listTables(selectedWs).catch(() => ({ tables: [] as Table[] })),
      ]);

      const stores = historiesRes.stores ?? [];
      const notebooks = notebooksRes.notebooks ?? [];
      const tables = tablesRes.tables ?? [];

      const searches = await Promise.allSettled([
        ...stores.map(async (store) => {
          const res = await searchHistoryEvents(selectedWs, store.id, q, 10);
          for (const event of res.events ?? []) {
            historyEvents.push({ event, storeName: store.name });
          }
        }),
        ...notebooks.map(async (nb) => {
          const pages = await semanticSearchPages(selectedWs, nb.id, q, 10);
          for (const page of pages ?? []) {
            wikiPages.push({ page, notebookName: nb.name });
          }
        }),
        ...tables.map(async (table) => {
          try {
            const rows = await semanticSearchTableRows(selectedWs, table.id, q, 10);
            for (const row of rows ?? []) {
              tableRows.push({ row, tableName: table.name, tableId: table.id });
            }
          } catch {}
        }),
      ]);

      const allFailed = searches.every((s) => s.status === "rejected");
      if (allFailed && searches.length > 0) {
        setError(
          "All searches failed. Check that the workspace has accessible resources."
        );
      }

      setResults({ historyEvents, wikiPages, tableRows });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
    setSearching(false);
  }, [query, selectedWs]);

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

  const show = {
    history: tab === "all" || tab === "history",
    wiki: tab === "all" || tab === "notebooks",
    tables: tab === "all" || tab === "tables",
  };

  const selectedWsName =
    workspaces.find((w) => w.id === selectedWs)?.name ?? null;

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
      <div className="mx-auto w-full max-w-[1120px] px-6 pt-8 pb-16">
        {/* Page header */}
        <div className="mb-6">
          <h1 className="font-display text-[32px] font-bold tracking-[-0.02em] text-foreground">
            Search
          </h1>
        </div>

        {/* Search bar */}
        <div className="mb-6 flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 transition-[border-color,box-shadow] focus-within:border-brand focus-within:shadow-[0_0_0_3px_rgba(249,115,22,0.25)]">
          <input
            type="text"
            placeholder={
              selectedWsName
                ? `Ask ${selectedWsName} anything…`
                : "Ask the workspace anything…"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSearch()}
            autoFocus
            className="flex-1 bg-transparent text-[15px] text-foreground placeholder:text-muted focus:outline-none"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim() || !selectedWs}
            className="inline-flex h-8 items-center justify-center rounded-md bg-brand px-3 text-[13px] font-medium text-white transition hover:bg-brand-hover disabled:opacity-50"
          >
            {searching ? "Searching…" : "Search"}
          </button>
        </div>

        {/* Tabs */}
        <div className="mb-6 flex gap-1 border-b border-border-subtle">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={
                "-mb-px border-b-2 px-3.5 py-2.5 text-[13px] transition-colors " +
                (tab === t.id
                  ? "border-brand font-medium text-brand"
                  : "border-transparent text-dim hover:text-foreground")
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {error && <p className="mb-4 text-[13px] text-red-400">{error}</p>}

        {searching && (
          <p className="py-8 text-center text-[13px] text-muted">
            Searching across history, notebooks, and tables…
          </p>
        )}

        {!searching && searchedQuery && totalResults === 0 && (
          <p className="py-8 text-center text-[13px] text-muted">
            No results found for &ldquo;{searchedQuery}&rdquo;
          </p>
        )}

        {!searching && (
          <div className="space-y-8">
            {show.history && results.historyEvents.length > 0 && (
              <section>
                <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
                  History · {results.historyEvents.length}
                </p>
                <div className="space-y-2">
                  {results.historyEvents.map(({ event, storeName }) => (
                    <div
                      key={event.id}
                      className="cursor-pointer rounded-lg border border-border-subtle bg-base px-4 py-3.5 transition-colors hover:border-brand"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span
                          className="inline-flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full font-display text-[10px] font-bold text-white"
                          style={{ background: "var(--color-agent)" }}
                        >
                          {event.agent_name[0]?.toUpperCase() || "A"}
                        </span>
                        <span className="text-[14px] font-semibold text-foreground">
                          {event.agent_name}
                        </span>
                        <span
                          className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.08em]"
                          style={{
                            background: "var(--color-agent-muted)",
                            color: "var(--color-agent)",
                          }}
                        >
                          agent
                        </span>
                        <span className="text-[12px] text-dim">·</span>
                        <span className="text-[12px] text-dim">
                          {event.event_type}
                        </span>
                        <span className="ml-auto font-mono text-[11px] text-muted">
                          {formatDate(event.created_at)}
                        </span>
                      </div>
                      <p className="line-clamp-3 text-[13px] leading-[1.55] text-dim">
                        {event.content}
                      </p>
                      <p className="mt-2 font-mono text-[10px] text-muted">
                        in {storeName}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {show.wiki && results.wikiPages.length > 0 && (
              <section>
                <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
                  Wiki · {results.wikiPages.length}
                </p>
                <div className="space-y-2">
                  {results.wikiPages.map(({ page, notebookName }) => (
                    <a
                      key={page.id}
                      href={`/notebooks?ws=${selectedWs}&nb=${page.notebook_id}&page=${page.id}`}
                      className="block rounded-lg border border-border-subtle bg-base px-4 py-3.5 transition-colors hover:border-brand"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-raised font-mono text-[10px] font-bold text-muted">
                          W
                        </span>
                        <span className="text-[14px] font-semibold text-foreground">
                          {page.name}
                        </span>
                        <span className="text-[12px] text-dim">·</span>
                        <span className="text-[12px] text-dim">{notebookName}</span>
                        <span className="ml-auto font-mono text-[11px] text-muted">
                          {formatDate(page.updated_at)}
                        </span>
                      </div>
                      <p className="line-clamp-2 text-[13px] leading-[1.55] text-dim">
                        {page.content_markdown?.slice(0, 240)}
                      </p>
                    </a>
                  ))}
                </div>
              </section>
            )}

            {show.tables && results.tableRows.length > 0 && (
              <section>
                <p className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
                  Tables · {results.tableRows.length}
                </p>
                <div className="space-y-2">
                  {results.tableRows.map(({ row, tableName, tableId }) => (
                    <a
                      key={row.id}
                      href={`/tables/${tableId}?ws=${selectedWs}`}
                      className="block rounded-lg border border-border-subtle bg-base px-4 py-3.5 transition-colors hover:border-brand"
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <span className="inline-flex items-center rounded bg-raised px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-dim">
                          tbl
                        </span>
                        <span className="text-[14px] font-semibold text-foreground">
                          {tableName}
                        </span>
                        <span className="ml-auto font-mono text-[11px] text-muted">
                          {formatDate(row.updated_at)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between rounded bg-surface px-2.5 py-2 font-mono text-[12px] text-dim">
                        <span className="truncate text-foreground">
                          {Object.entries(row.data)
                            .slice(0, 4)
                            .map(([k, v]) => `${k}: ${String(v)}`)
                            .join(" · ")}
                        </span>
                      </div>
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
