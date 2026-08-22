"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ArrowUpDown, LayoutGrid, Table2 } from "lucide-react";

import { Select } from "@/components/ui/select";
import { appFacets, getApp, getTable, installApp, listAppRows } from "@/lib/api";
import type { AppFacets, MiniProgramManifest, Table, TableColumn, TableRow } from "@/lib/types";

import AppBulkBar from "./AppBulkBar";
import AppCard from "./AppCard";
import AppDetail from "./AppDetail";
import AppSkillsBanner from "./AppSkillsBanner";
import { cellLabels, cellText, displayTimestamp } from "./cells";

const PAGE_SIZE = 60;
// Rows enrich in the background; re-poll while any on screen is still bare.
const ENRICH_POLL_MS = 6000;
type Layout = "table" | "cards";
type SortOrder = "asc" | "desc";

const DERIVED = [
  { key: "duplicates", label: "Duplicates" },
  { key: "broken", label: "Broken links" },
  { key: "untagged", label: "Without topics" },
] as const;

function CellValue({ row, column }: { row: TableRow; column: TableColumn }) {
  const value = row.data[column.id];

  if (column.type === "multiselect") {
    const labels = cellLabels(row, column.id);
    if (labels.length === 0) return <span className="text-dim">—</span>;
    return (
      <span className="flex flex-wrap gap-1">
        {labels.map((label) => (
          <span key={label} className="rounded bg-raised px-1.5 py-0.5 text-[11px]">
            {label}
          </span>
        ))}
      </span>
    );
  }

  const text = value == null ? "" : String(value);
  if (!text) return <span className="text-dim">—</span>;

  if (column.type === "url") {
    return (
      <a
        href={text}
        target="_blank"
        rel="noopener noreferrer"
        className="block max-w-72 truncate text-brand hover:underline"
      >
        {text}
      </a>
    );
  }

  if (column.name === "Saved") return <>{displayTimestamp(text)}</>;
  return <span className="block max-w-80 truncate">{text}</span>;
}

export default function AppView({ slug }: { slug: string }) {
  const [manifest, setManifest] = useState<MiniProgramManifest | null>(null);
  const [table, setTable] = useState<Table | null>(null);
  const [facets, setFacets] = useState<AppFacets | null>(null);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  const [defaultViewId, setDefaultViewId] = useState<string | null>(null);
  const [topic, setTopic] = useState<string | null>(null);
  const [derived, setDerived] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>("table");
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");
  const [openRowId, setOpenRowId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const sentinelRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);
  const lastSelectedIndexRef = useRef<number | null>(null);

  const refreshFacets = useCallback(async () => {
    try {
      setFacets(await appFacets(slug));
    } catch {
      /* counts are decoration; a failure here must not blank the list */
    }
  }, [slug]);

  const loadPage = useCallback(
    async (
      offset: number,
      viewId: string | null = defaultViewId,
      preserveLoadedRows = false
    ) => {
      const requestId = ++requestIdRef.current;
      const page = await listAppRows(slug, {
        topic: topic ?? undefined,
        filter: derived ?? undefined,
        view_id: viewId ?? undefined,
        sort_by: sortBy ?? undefined,
        sort_order: sortBy ? sortOrder : undefined,
        limit: PAGE_SIZE,
        offset,
      });
      if (requestId !== requestIdRef.current) return;
      setTotal(page.total);
      setHasMore(page.has_more);
      setRows((previous) => {
        if (offset > 0) return [...previous, ...page.rows];
        if (!preserveLoadedRows) return page.rows;
        const refreshedIds = new Set(page.rows.map((row) => row.id));
        return [...page.rows, ...previous.filter((row) => !refreshedIds.has(row.id))];
      });
    },
    [slug, topic, derived, defaultViewId, sortBy, sortOrder]
  );

  const init = useCallback(async () => {
    try {
      const app = await getApp(slug);
      setManifest(app.manifest);
      const loadedTable = await getTable(app.table_id);
      const initialViewId = loadedTable.views?.find((view) => view.name === "Recent")?.id ?? null;
      setTable(loadedTable);
      setDefaultViewId(initialViewId);
      setMissing(false);
      await Promise.all([loadPage(0, initialViewId), refreshFacets()]);
    } catch (e) {
      if (e instanceof Error && /not set up|404/i.test(e.message)) setMissing(true);
      else setError("Couldn't load this app.");
    } finally {
      setLoading(false);
    }
    // loadPage is intentionally omitted: it changes with every filter, and
    // re-running init on a filter change would refetch the manifest too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, refreshFacets]);

  useEffect(() => {
    void init();
  }, [init]);

  // Any filter change resets to page one.
  useEffect(() => {
    if (loading || missing || !manifest || !table) return;
    setSelected(new Set());
    void loadPage(0);
  }, [
    topic,
    derived,
    defaultViewId,
    sortBy,
    sortOrder,
    loadPage,
    loading,
    missing,
    manifest,
    table,
  ]);

  // Infinite scroll.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !hasMore || loadingMore) return;
    const observer = new IntersectionObserver(async ([entry]) => {
      if (!entry.isIntersecting) return;
      setLoadingMore(true);
      try {
        await loadPage(rows.length);
      } finally {
        setLoadingMore(false);
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, rows.length, loadPage]);

  const pendingRowIds = useMemo(() => {
    const enriched = manifest?.enriched_columns ?? [];
    if (!enriched.length) return new Set<string>();
    return new Set(rows.filter((r) => enriched.every((c) => !r.data[c])).map((r) => r.id));
  }, [rows, manifest]);

  useEffect(() => {
    if (pendingRowIds.size === 0) return;
    const t = setTimeout(() => {
      void loadPage(0, defaultViewId, true);
      void refreshFacets();
    }, ENRICH_POLL_MS);
    return () => clearTimeout(t);
  }, [pendingRowIds, defaultViewId, loadPage, refreshFacets]);

  const afterMutation = useCallback(async () => {
    setSelected(new Set());
    await Promise.all([loadPage(0), refreshFacets()]);
  }, [loadPage, refreshFacets]);

  const toggleSelected = (id: string, index: number, range: boolean) => {
    const rangeStart = lastSelectedIndexRef.current;
    lastSelectedIndexRef.current = index;

    setSelected((previous) => {
      if (range && rangeStart !== null) {
        const start = Math.min(rangeStart, index);
        const end = Math.max(rangeStart, index);
        const next = new Set(previous);
        rows.slice(start, end + 1).forEach((row) => next.add(row.id));
        return next;
      }

      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAllVisible = () =>
    setSelected((previous) => {
      const allVisibleSelected = rows.every((row) => previous.has(row.id));
      if (allVisibleSelected) return new Set();
      const next = new Set(previous);
      rows.forEach((row) => next.add(row.id));
      return next;
    });

  const changeSort = (columnId: string) => {
    if (sortBy === columnId) {
      setSortOrder((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(columnId);
    setSortOrder("asc");
  };

  const openRow = useMemo(() => rows.find((r) => r.id === openRowId) ?? null, [rows, openRowId]);
  const columns = useMemo(
    () => [...(table?.columns ?? [])].sort((a, b) => a.order - b.order),
    [table]
  );

  if (loading) return <div className="p-8 text-[13px] text-muted-foreground">Loading…</div>;

  if (missing) {
    return (
      <div className="mx-auto max-w-md px-8 py-16 text-center">
        <h1 className="font-display text-[22px] font-bold text-foreground">Nothing here yet</h1>
        <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">
          Set this up and anything you save lands here, summarised and sorted by topic.
        </p>
        <button
          type="button"
          onClick={async () => {
            setLoading(true);
            try {
              await installApp(slug);
              await init();
            } catch {
              setMissing(false);
              setError("Couldn't set up this app.");
              setLoading(false);
            }
          }}
          className="mt-5 cursor-pointer rounded-lg bg-brand px-5 py-2.5 text-[13.5px] font-semibold text-white hover:bg-brand-hover"
        >
          Set up
        </button>
      </div>
    );
  }

  if (error || !manifest || !table) {
    return <div className="p-8 text-[13px] text-red-500">{error || "Couldn't load this app."}</div>;
  }

  const filtering = !!(topic || derived);

  return (
    <div
      className={
        openRow
          ? "grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_420px]"
          : "grid h-full min-h-0 min-w-0 grid-cols-1 overflow-hidden"
      }
    >
      <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="font-display text-[20px] font-bold tracking-tight text-foreground">
              {manifest.title}
            </h1>
            <span className="text-[12px] text-dim">
              {filtering ? `${total} of ${facets?.total ?? total}` : `${total} saved`}
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Select
              aria-label="Filter bookmarks"
              value={derived ?? ""}
              onChange={(v) => setDerived(v || null)}
              options={[
                { value: "", label: "All bookmarks" },
                ...DERIVED.filter((item) => (facets?.[item.key] ?? 0) > 0).map((item) => ({
                  value: item.key,
                  label: `${item.label} (${facets?.[item.key]})`,
                })),
              ]}
              className="px-2.5 py-1.5 text-[12px]"
            />

            <Select
              aria-label="Filter by topic"
              value={topic ?? ""}
              onChange={(v) => setTopic(v || null)}
              options={[
                { value: "", label: "All topics" },
                ...(facets?.topics ?? []).map((item) => ({
                  value: item.label,
                  label: `${item.label} (${item.count})`,
                })),
              ]}
              className="px-2.5 py-1.5 text-[12px]"
            />

            {filtering && (
              <button
                type="button"
                onClick={() => {
                  setDerived(null);
                  setTopic(null);
                }}
                className="text-[12px] text-muted-foreground hover:text-foreground"
              >
                Clear filters
              </button>
            )}

            <div className="ml-auto flex items-center gap-2">
              <Select
                aria-label="Sort bookmarks"
                value={sortBy ?? ""}
                onChange={(columnId) => {
                  setSortBy(columnId || null);
                  setSortOrder("asc");
                }}
                options={[
                  { value: "", label: "Default order" },
                  ...columns.map((column) => ({
                    value: column.id,
                    label: `Sort by ${column.name}`,
                  })),
                ]}
                className="px-2.5 py-1.5 text-[12px]"
              />

              {sortBy && (
                <button
                  type="button"
                  onClick={() =>
                    setSortOrder((current) => (current === "asc" ? "desc" : "asc"))
                  }
                  aria-label={`Sort ${sortOrder === "asc" ? "descending" : "ascending"}`}
                  className="rounded-md border border-border p-1.5 text-muted-foreground hover:bg-raised hover:text-foreground"
                >
                  {sortOrder === "asc" ? (
                    <ArrowUp className="h-4 w-4" />
                  ) : (
                    <ArrowDown className="h-4 w-4" />
                  )}
                </button>
              )}

              <div className="flex rounded-md border border-border p-0.5">
                <button
                  type="button"
                  onClick={() => setLayout("table")}
                  aria-label="Table view"
                  aria-pressed={layout === "table"}
                  className={`rounded p-1.5 ${
                    layout === "table"
                      ? "bg-raised text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Table2 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setLayout("cards")}
                  aria-label="Card view"
                  aria-pressed={layout === "cards"}
                  className={`rounded p-1.5 ${
                    layout === "cards"
                      ? "bg-raised text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <LayoutGrid className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </header>

        <AppSkillsBanner slug={slug} />

        <div className="scroll-thin min-h-0 flex-1 overflow-auto">
          {rows.length === 0 ? (
            filtering ? (
              <p className="py-12 text-center text-[13px] text-muted-foreground">
                Nothing matches that filter.
              </p>
            ) : (
              <div className="mx-auto max-w-md py-14 text-center">
                <h2 className="text-[15px] font-semibold text-foreground">
                  {manifest.empty_state.title}
                </h2>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">
                  {manifest.empty_state.description}
                </p>
                <Link
                  href={manifest.empty_state.action.href}
                  className="mt-4 rounded-lg bg-brand px-3.5 py-2 text-[12.5px] font-semibold text-white hover:bg-brand-hover"
                >
                  {manifest.empty_state.action.label}
                </Link>
              </div>
            )
          ) : layout === "table" ? (
            <table data-testid="bookmarks-table" className="min-w-full border-separate border-spacing-0 text-left text-[12px]">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr>
                  <th className="w-10 border-b border-r border-border px-3 py-2">
                    <input
                      type="checkbox"
                      checked={rows.length > 0 && rows.every((row) => selected.has(row.id))}
                      onChange={toggleAllVisible}
                      aria-label="Select all visible bookmarks"
                      className="accent-[var(--brand)]"
                    />
                  </th>
                  {columns.map((column) => (
                    <th
                      key={column.id}
                      className="whitespace-nowrap border-b border-r border-border p-0 font-medium text-muted-foreground last:border-r-0"
                      style={{ minWidth: Math.max(column.width || 120, 120) }}
                    >
                      <button
                        type="button"
                        onClick={() => changeSort(column.id)}
                        aria-label={`Sort by ${column.name}`}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-raised hover:text-foreground"
                      >
                        {column.name}
                        {sortBy === column.id ? (
                          sortOrder === "asc" ? (
                            <ArrowUp className="h-3.5 w-3.5" />
                          ) : (
                            <ArrowDown className="h-3.5 w-3.5" />
                          )
                        ) : (
                          <ArrowUpDown className="h-3.5 w-3.5 opacity-40" />
                        )}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={row.id}
                    // The whole row opens the detail pane, not just the title
                    // cell — a row that highlights on hover but only responds
                    // on one word reads as broken. The checkbox cell stops
                    // propagation so selecting still works.
                    onClick={() => setOpenRowId(row.id === openRowId ? null : row.id)}
                    className={`cursor-pointer ${
                      row.id === openRowId ? "bg-brand/5" : "hover:bg-raised/60"
                    }`}
                  >
                    <td
                      className="border-b border-r border-border px-3 py-2"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(row.id)}
                        onMouseDown={(event) => {
                          event.preventDefault();
                          toggleSelected(row.id, index, event.shiftKey);
                        }}
                        onChange={() => undefined}
                        aria-label={`Select ${cellText(row, manifest.detail.title) || "bookmark"}`}
                        className="accent-[var(--brand)]"
                      />
                    </td>
                    {columns.map((column) => (
                      <td
                        key={column.id}
                        className="border-b border-r border-border px-3 py-2 text-foreground last:border-r-0"
                      >
                        {column.id === manifest.detail.title ? (
                          <span className="block max-w-80 truncate font-medium">
                            {cellText(row, column.id) || "Untitled"}
                          </span>
                        ) : (
                          <CellValue row={row} column={column} />
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div
              data-testid="bookmarks-cards"
              className="grid grid-cols-1 gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3"
            >
              {rows.map((row, index) => (
                <AppCard
                  key={row.id}
                  row={row}
                  manifest={manifest}
                  pendingEnrichment={pendingRowIds.has(row.id)}
                  active={row.id === openRowId}
                  selected={selected.has(row.id)}
                  onToggleSelected={(range) => toggleSelected(row.id, index, range)}
                  onOpen={() => setOpenRowId(row.id === openRowId ? null : row.id)}
                />
              ))}
            </div>
          )}

          <div ref={sentinelRef} className="h-8" />
          {loadingMore && (
            <p className="pb-4 text-center text-[12px] text-dim">Loading more…</p>
          )}
        </div>

        {selected.size > 0 && (
          <AppBulkBar
            slug={slug}
            selectedIds={[...selected]}
            knownTopics={(facets?.topics ?? []).map((t) => t.label)}
            onClear={() => setSelected(new Set())}
            onDone={afterMutation}
          />
        )}
      </div>

      {openRow && (
        <AppDetail
          row={openRow}
          slug={slug}
          manifest={manifest}
          table={table}
          knownTopics={(facets?.topics ?? []).map((t) => t.label)}
          onClose={() => setOpenRowId(null)}
          onChanged={afterMutation}
        />
      )}
    </div>
  );
}
