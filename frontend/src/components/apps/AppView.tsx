"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Copy, LayoutGrid, Search, Table2, TagIcon } from "lucide-react";

import { appFacets, getApp, getTable, installApp, listAppRows } from "@/lib/api";
import type {
  AppFacets,
  MiniProgramManifest,
  Table,
  TableRow,
  TableView,
  TableViewLayout,
} from "@/lib/types";

import AppBulkBar from "./AppBulkBar";
import AppCard from "./AppCard";
import AppDetail from "./AppDetail";
import { cellText } from "./cells";

const PAGE_SIZE = 60;
const SEARCH_DEBOUNCE_MS = 250;
// Rows enrich in the background; re-poll while any on screen is still bare.
const ENRICH_POLL_MS = 6000;

function layoutOf(view: TableView | null): TableViewLayout {
  return view?.layout === "cards" ? "cards" : view ? "table" : "cards";
}

/** The derived filters, in Raindrop's model: not separate screens, just
 *  filters over the same list with a count beside each. */
const DERIVED = [
  { key: "duplicates", label: "Duplicates", icon: Copy },
  { key: "broken", label: "Broken", icon: AlertTriangle },
  { key: "untagged", label: "Untagged", icon: TagIcon },
] as const;

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

  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [topic, setTopic] = useState<string | null>(null);
  const [derived, setDerived] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [openRowId, setOpenRowId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const sentinelRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  // Debounce typing so a search doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQuery(queryInput), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [queryInput]);

  const refreshFacets = useCallback(async () => {
    try {
      setFacets(await appFacets(slug));
    } catch {
      /* counts are decoration; a failure here must not blank the list */
    }
  }, [slug]);

  const loadPage = useCallback(
    async (offset: number) => {
      const requestId = ++requestIdRef.current;
      const page = await listAppRows(slug, {
        q: query,
        topic: topic ?? undefined,
        filter: derived ?? undefined,
        view_id: activeViewId ?? undefined,
        limit: PAGE_SIZE,
        offset,
      });
      if (requestId !== requestIdRef.current) return;
      setTotal(page.total);
      setHasMore(page.has_more);
      setRows((prev) => (offset === 0 ? page.rows : [...prev, ...page.rows]));
    },
    [slug, query, topic, derived, activeViewId]
  );

  const init = useCallback(async () => {
    try {
      const app = await getApp(slug);
      setManifest(app.manifest);
      setTable(await getTable(app.table_id));
      setMissing(false);
      await Promise.all([loadPage(0), refreshFacets()]);
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

  // Any filter/search change resets to page one.
  useEffect(() => {
    if (loading) return;
    setSelected(new Set());
    void loadPage(0);
  }, [query, topic, derived, activeViewId, loadPage, loading]);

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

  const activeView = useMemo(
    () => table?.views?.find((v) => v.id === activeViewId) ?? null,
    [table, activeViewId]
  );
  const layout = layoutOf(activeView);

  const pendingRowIds = useMemo(() => {
    const enriched = manifest?.enriched_columns ?? [];
    if (!enriched.length) return new Set<string>();
    return new Set(rows.filter((r) => enriched.every((c) => !r.data[c])).map((r) => r.id));
  }, [rows, manifest]);

  useEffect(() => {
    if (pendingRowIds.size === 0) return;
    const t = setTimeout(() => {
      void loadPage(0);
      void refreshFacets();
    }, ENRICH_POLL_MS);
    return () => clearTimeout(t);
  }, [pendingRowIds, loadPage, refreshFacets]);

  const afterMutation = useCallback(async () => {
    setSelected(new Set());
    await Promise.all([loadPage(0), refreshFacets()]);
  }, [loadPage, refreshFacets]);

  const toggleSelected = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const openRow = useMemo(() => rows.find((r) => r.id === openRowId) ?? null, [rows, openRowId]);

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
            await installApp(slug);
            setLoading(true);
            await init();
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

  const filtering = !!(query || topic || derived);

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-border px-6 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <h1 className="font-display text-[20px] font-bold tracking-tight text-foreground">
                {manifest.title}
              </h1>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">{manifest.tagline}</p>
            </div>
            <span className="text-[12px] text-dim">
              {filtering ? `${total} of ${facets?.total ?? total}` : `${total} saved`}
            </span>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-dim" />
              <input
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                placeholder="Search everything"
                className="w-60 rounded-lg border border-border bg-base py-1.5 pl-8 pr-3 text-[12.5px] text-foreground placeholder:text-dim focus:border-brand focus:outline-none"
              />
            </div>

            {(table.views ?? []).map((view) => (
              <button
                key={view.id}
                type="button"
                data-testid="view-switch"
                onClick={() => setActiveViewId(view.id === activeViewId ? null : view.id)}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] ${
                  view.id === activeViewId
                    ? "bg-brand/15 font-medium text-brand"
                    : "text-muted-foreground hover:bg-raised hover:text-foreground"
                }`}
              >
                {view.layout === "cards" ? (
                  <LayoutGrid className="h-3.5 w-3.5" />
                ) : (
                  <Table2 className="h-3.5 w-3.5" />
                )}
                {view.name}
              </button>
            ))}

            <Link
              href={`/tables/${table.id}`}
              className="ml-auto text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              Open as table
            </Link>
          </div>

          {facets && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {DERIVED.filter((d) => (facets[d.key] ?? 0) > 0).map((d) => {
                const Icon = d.icon;
                const on = derived === d.key;
                return (
                  <button
                    key={d.key}
                    type="button"
                    data-testid="derived-chip"
                    onClick={() => setDerived(on ? null : d.key)}
                    className={`inline-flex cursor-pointer items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                      on
                        ? "bg-amber-500 text-white"
                        : "bg-amber-500/10 text-amber-700 hover:bg-amber-500/20 dark:text-amber-400"
                    }`}
                  >
                    <Icon className="h-3 w-3" />
                    {d.label} {facets[d.key]}
                  </button>
                );
              })}
              {facets.topics.map((t) => (
                <button
                  key={t.label}
                  type="button"
                  data-testid="topic-chip"
                  onClick={() => setTopic(t.label === topic ? null : t.label)}
                  className={`cursor-pointer rounded-full px-2.5 py-1 text-[11px] font-medium ${
                    t.label === topic
                      ? "bg-brand text-white"
                      : "bg-raised text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t.label} <span className="opacity-60">{t.count}</span>
                </button>
              ))}
            </div>
          )}
        </header>

        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {rows.length === 0 ? (
            <p className="py-12 text-center text-[13px] text-muted-foreground">
              {filtering ? "Nothing matches that filter." : "Nothing saved yet."}
            </p>
          ) : layout === "cards" ? (
            <div
              data-testid="card-grid"
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
            >
              {rows.map((row) => (
                <AppCard
                  key={row.id}
                  row={row}
                  manifest={manifest}
                  pendingEnrichment={pendingRowIds.has(row.id)}
                  active={row.id === openRowId}
                  selected={selected.has(row.id)}
                  onToggleSelected={() => toggleSelected(row.id)}
                  onOpen={() => setOpenRowId(row.id === openRowId ? null : row.id)}
                />
              ))}
            </div>
          ) : (
            <div data-testid="compact-list" className="divide-y divide-border rounded-xl border border-border">
              {rows.map((row) => (
                <div
                  key={row.id}
                  className={`flex items-baseline gap-3 px-4 py-2.5 hover:bg-raised ${
                    row.id === openRowId ? "bg-brand/5" : ""
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(row.id)}
                    onChange={() => toggleSelected(row.id)}
                    aria-label="Select row"
                    className="cursor-pointer accent-[var(--brand)]"
                  />
                  <button
                    type="button"
                    onClick={() => setOpenRowId(row.id === openRowId ? null : row.id)}
                    className="flex min-w-0 flex-1 cursor-pointer items-baseline gap-3 text-left"
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                      {cellText(row, manifest.detail.title) || "Untitled"}
                    </span>
                    <span className="shrink-0 text-[11.5px] text-dim">
                      {cellText(row, manifest.detail.subtitle)}
                    </span>
                  </button>
                </div>
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
          knownTopics={(facets?.topics ?? []).map((t) => t.label)}
          onClose={() => setOpenRowId(null)}
          onChanged={afterMutation}
        />
      )}
    </div>
  );
}
