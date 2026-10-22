"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceTable";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { CalendarDays, ChevronDown, Search, Trash2 } from "lucide-react";
import { Popover } from "radix-ui";
import { Select } from "@/components/ui/select";
import { rmListAllTraces } from "@/lib/api";
import { traceScore, traceScoreLabel, traceCredits } from "./trace-metrics";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmTraceSummary } from "@/lib/types";
import { selectRange, sortTraces, toggleAllVisible, type TraceSortKey, type TraceSortDirection } from "./trace-selection";
import { matchesTraceFilters, traceSourceId, traceSourceKey, traceSourceName, type TraceFilters } from "./trace-sources";
import TraceSourceNameDialog from "./TraceSourceNameDialog";
import { BehaviorChips, OutcomeTag, QuoteSnippet, cleanSnippet, groupBySession } from "@/components/behaviors/behavior-ui";
import { stepWindow, traceStepHref, type SearchResponse, type SearchResult } from "@/lib/behaviors-api";

/** Search results that replace the plain list: rows come from `results`, in relevance order until a column is sorted. */
export interface TraceMatches {
  results: SearchResult[];
  mode: SearchResponse["mode"] | null;
  query: string;
  /** Behavior IDs the search was filtered to; a key for "this search", not re-applied here. */
  behaviors: string[];
  loading: boolean;
}

/** A search row for a trace that is not in the loaded list (e.g. shared for review). */
function summaryFromResult(r: SearchResult): RmTraceSummary {
  return {
    id: r.trace_id, external_id: null, title: r.title || r.input || "Untitled trace", source_format: "", step_count: 0,
    positive_count: 0, negative_count: 0, comment_count: 0, label_error_count: 0, latest_score: null, created_at: r.created_at,
    ...(r.agent && { agent: r.agent }),
  };
}

const COLUMNS: { key: TraceSortKey; label: string; className: string }[] = [
  { key: "title", label: "Trace", className: "" },
  { key: "source", label: "Source", className: "w-36" },
  { key: "steps", label: "Steps", className: "w-16 text-right" },
  { key: "comments", label: "Comments", className: "w-24 text-right" },
  { key: "credit", label: "Avg. credit", className: "w-24 text-right" },
  { key: "minCredit", label: "Min. credit", className: "w-24 text-right" },
  { key: "maxCredit", label: "Max. credit", className: "w-24 text-right" },
  { key: "reward", label: "Trace score", className: "w-28 text-right" },
  { key: "imported", label: "Imported", className: "w-48 text-right" },
];

/**
 * Browse rows open the trace; checkboxes and shift-click select ranges.
 * In the training picker, clicking anywhere on a row toggles it.
 */
function LatestTraceTable({
  traces,
  selected,
  onSelectedChange,
  mode,
  onDelete,
  deletingId,
  selectionDisabled = false,
  toolbar,
  toolbarActions,
  matches = null,
  behaviorsByTrace,
}: {
  traces: RmTraceSummary[];
  selected: Set<string>;
  onSelectedChange: (next: Set<string>) => void;
  mode: "browse" | "picker";
  onDelete?: (trace: RmTraceSummary) => void;
  deletingId?: string | null;
  selectionDisabled?: boolean;
  /** Controls rendered at the start of the filter row (browse search, behavior filter…). */
  toolbar?: ReactNode;
  /** Actions at the right edge of the trace filter row. */
  toolbarActions?: ReactNode;
  matches?: TraceMatches | null;
  /** Behavior hits and outcomes per trace, for the Behaviors column of the plain list. */
  behaviorsByTrace?: Map<string, SearchResult>;
}) {
  const [dateOpen, setDateOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("all");
  const [filters, setFilters] = useState<TraceFilters>({ source: "all", from: "", through: "" });
  const [sourceNames, setSourceNames] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<{ key: TraceSortKey; direction: TraceSortDirection }>({ key: "imported", direction: "descending" });
  // Search results keep their relevance order until a column is sorted for this search.
  const matchKey = matches ? `${matches.query.trim()}|${matches.behaviors.join(",")}` : null;
  const [sortedFor, setSortedFor] = useState<string | null>(null);
  const relevance = matchKey !== null && sortedFor !== matchKey;
  // Keep the browse list's ordering when opening a trace and coming back. The
  // training picker has its own preference so it cannot overwrite the list.
  const sortStorageKey = `stash-traces-sort:${mode}`;
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(sortStorageKey) ?? "null");
      if (saved && COLUMNS.some((column) => column.key === saved.key)
        && (saved.direction === "ascending" || saved.direction === "descending")) setSort(saved);
    } catch { /* Sorting still works when browser storage is unavailable. */ }
  }, [sortStorageKey]);
  // Keep the anchor by ID so incoming traces cannot move it during a background refresh.
  const anchor = useRef<string | null>(null);

  useEffect(() => { if (selected.size === 0) anchor.current = null; }, [selected.size]);

  const [searchResults, setSearchResults] = useState<RmTraceSummary[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  useEffect(() => {
    if (!query.trim()) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      void rmListAllTraces(query).then((results) => {
        if (!cancelled) { setSearchResults(results); setSearchError(null); }
      }).catch(() => { if (!cancelled) setSearchError("Couldn’t search traces. Edit your search to try again."); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, traces]);
  const searching = (!!query.trim() && searchResults === null && !searchError) || !!matches?.loading;
  const namedTrace = (trace: RmTraceSummary) => sourceNames[traceSourceKey(trace)]
    ? { ...trace, source_name: sourceNames[traceSourceKey(trace)] } : trace;
  const sources = Array.from(new Map(traces.map((trace) => [traceSourceKey(trace), namedTrace(trace)])).values())
    .sort((a, b) => traceSourceName(a).localeCompare(traceSourceName(b)));
  const selectedSource = sources.find((trace) => traceSourceKey(trace) === filters.source);
  // Search can return traces shared for review; only the loaded picker set is trainable.
  const selectableIds = new Set(traces.map((trace) => trace.id));
  const loadedById = new Map(traces.map((trace) => [trace.id, trace]));
  const matchById = new Map((matches?.results ?? []).map((r) => [r.trace_id, r]));
  const infoFor = (id: string) => matchById.get(id) ?? behaviorsByTrace?.get(id);
  const rows = matches ? matches.results.map((r) => loadedById.get(r.trace_id) ?? summaryFromResult(r))
    : query.trim() ? searchResults ?? [] : traces;
  const filtered = rows.map(namedTrace)
    .filter((trace) => (mode !== "picker" || selectableIds.has(trace.id)) && matchesTraceFilters(trace, filters))
    .filter((trace) => assessmentFilter === "all"
    || (assessmentFilter === "scored" && traceScore(trace) !== null)
    || (assessmentFilter === "unscored" && traceScore(trace) === null));
  const sortedRows = relevance ? filtered : sortTraces(filtered, sort.key, sort.direction, "automatic");
  // Search results from one session sit together under a session row.
  const groups = relevance
    ? groupBySession(sortedRows.map((t) => matchById.get(t.id)!)).map((g) => ({ session: g.session, rows: g.rows.map((r) => sortedRows.find((t) => t.id === r.trace_id)!) }))
    : [{ session: null, rows: sortedRows }];
  const visible = groups.flatMap((g) => g.rows);
  const browse = mode === "browse";
  const loadingMatches = !!matches?.loading;
  const visibleIds = visible.filter((t) => mode === "picker" || t.can_score !== false).map((t) => t.id);
  const selectedVisible = visibleIds.filter((id) => selected.has(id)).length;
  const hiddenSelected = traces.filter((trace) => selected.has(trace.id)).length - selectedVisible;
  const hasFilters = filters.source !== "all" || !!filters.from || !!filters.through;
  const dateLabel = (value: string) => value ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
  const dateSummary = filters.from && filters.through ? `${dateLabel(filters.from)} – ${dateLabel(filters.through)}` : filters.from ? `Since ${dateLabel(filters.from)}` : filters.through ? `Until ${dateLabel(filters.through)}` : "Imported date";
  const invalidDates = !!filters.from && !!filters.through && filters.from > filters.through;

  function changeFilters(next: Partial<TraceFilters>) {
    setFilters((current) => ({ ...current, ...next }));
    anchor.current = null;
  }

  function toggleRow(id: string, shiftKey: boolean) {
    if (selectionDisabled) return;
    const index = visibleIds.indexOf(id);
    if (index < 0) return;
    const value = !selected.has(id);
    const from = anchor.current === null ? -1 : visibleIds.indexOf(anchor.current);
    if (shiftKey && from >= 0) {
      onSelectedChange(selectRange(visibleIds, selected, from, index, value));
    } else {
      onSelectedChange(selectRange(visibleIds, selected, index, index, value));
    }
    anchor.current = id;
  }

  return (
    <div>
      <div role="group" aria-label="Trace filters" className="mb-1.5 flex flex-wrap items-center gap-1.5">
        {toolbar}
        {mode === "picker" && <label className="flex h-[26px] w-56 items-center gap-1.5 rounded-[4px] border border-border bg-background px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearchResults(null);
              setSearchError(null);
              anchor.current = null;
            }}
            placeholder="Search traces"
            aria-label="Search titles and trace content"
            className="min-w-0 flex-1 bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>}
        {mode === "browse" && <Select aria-label="Filter traces" value={assessmentFilter} onChange={(value) => { setAssessmentFilter(value); anchor.current = null; }} className="h-[26px] w-24 rounded-[4px] px-2 text-[11px]" contentClassName="rounded-[4px] [&_[role=option]]:text-[11px]" options={[{ value: "all", label: "All traces" }, { value: "scored", label: "Scored" }, { value: "unscored", label: "Unscored" }]} />}
        <div className="flex items-center gap-1">
          <Select aria-label="Filter by source" value={filters.source} onChange={(source) => changeFilters({ source })} className="h-[26px] w-28 rounded-[4px] px-2 text-[11px]" contentClassName="rounded-[4px] [&_[role=option]]:text-[11px]" options={[
            { value: "all", label: "All sources" },
            ...sources.map((trace) => ({ value: traceSourceKey(trace), label: traceSourceName(trace) })),
          ]} />
          {selectedSource && selectedSource.can_score !== false && <TraceSourceNameDialog
            key={filters.source}
            sourceId={traceSourceId(selectedSource)}
            name={traceSourceName(selectedSource)}
            onRenamed={(name) => setSourceNames((current) => ({ ...current, [filters.source]: name }))}
          />}
        </div>
        <Popover.Root open={dateOpen} onOpenChange={setDateOpen}>
          <Popover.Trigger asChild>
            <button type="button" aria-label="Filter by imported date" title={dateSummary} className={cn("inline-flex h-[26px] items-center gap-1.5 rounded-[4px] border px-2 text-[11px] whitespace-nowrap focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30", filters.from || filters.through ? "border-foreground/30 bg-surface text-foreground" : "border-border bg-background text-muted-foreground")}><CalendarDays className="size-3" />{dateSummary}<ChevronDown className="size-3" /></button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content align="start" sideOffset={5} aria-label="Imported date range" className="z-50 w-64 rounded-[4px] border border-border bg-popover p-3 text-xs text-popover-foreground shadow-sm outline-none">
              <h3 className="mb-3 text-xs font-medium">Imported date</h3>
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1 text-[11px] text-muted-foreground">From<input type="date" aria-label="Imported from" value={filters.from} max={filters.through || undefined} onChange={(e) => changeFilters({ from: e.target.value })} className="h-7 min-w-0 rounded-[4px] border border-border bg-background px-1.5 text-[11px] text-foreground" /></label>
                <label className="grid gap-1 text-[11px] text-muted-foreground">Through<input type="date" aria-label="Imported through" value={filters.through} min={filters.from || undefined} onChange={(e) => changeFilters({ through: e.target.value })} className="h-7 min-w-0 rounded-[4px] border border-border bg-background px-1.5 text-[11px] text-foreground" /></label>
              </div>
              <div className="mt-3 flex justify-between gap-2"><Button variant="ghost" size="xs" onClick={() => changeFilters({ from: "", through: "" })}>Clear dates</Button><Popover.Close asChild><Button variant="outline" size="xs">Done</Button></Popover.Close></div>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
        {hasFilters && <Button variant="ghost" size="xs" className="h-[26px] px-1.5 text-[11px]" onClick={() => changeFilters({ source: "all", from: "", through: "" })}>Clear filters</Button>}


        {toolbarActions && <div className="ml-auto flex items-center">{toolbarActions}</div>}
      </div>

      {(mode === "picker" || selected.size > 0) && <div className="mb-3 flex items-center gap-3 text-[12px] text-muted-foreground">
        <Button variant="outline" size="xs" disabled={selectionDisabled || searching || !!searchError || visibleIds.length === 0} onClick={() => { onSelectedChange(new Set(visibleIds)); anchor.current = null; }}>Select only shown</Button>
        <span>{selectedVisible} shown selected{hiddenSelected > 0 && `, ${hiddenSelected} selected outside these filters`}</span>
      </div>}
      {invalidDates && <p role="alert" className="mb-3 text-xs text-red-600">The end date must be on or after the start date.</p>}
      {searchError && <p role="alert" className="mb-3 text-sm text-red-600">{searchError}</p>}
      <div className="overflow-x-auto rounded-[4px] border border-border">
        <table aria-label="Traces" className={cn("w-full table-fixed border-collapse text-[13px]", browse ? "min-w-[1400px]" : "min-w-[1140px]")}>
          <thead>
            <tr className={cn("border-b border-border bg-surface text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase", mode === "browse" && "h-7 [&>th]:py-0")}>
              <th className="w-8 py-2 pl-3">
                <Checkbox
                  checked={visibleIds.length > 0 && selectedVisible === visibleIds.length}
                  indeterminate={selectedVisible > 0 && selectedVisible < visibleIds.length}
                  disabled={selectionDisabled || visibleIds.length === 0}
                  onClick={() => { onSelectedChange(toggleAllVisible(visibleIds, selected)); anchor.current = null; }}
                  label="Select all shown traces"
                />
              </th>
              {COLUMNS.map((column) => (
                <Fragment key={column.key}>
                <th scope="col" aria-sort={!relevance && sort.key === column.key ? sort.direction : "none"} className={cn("px-3 py-2 font-medium", column.className)}>
                  <button
                    type="button"
                    className="cursor-pointer whitespace-nowrap hover:text-foreground"
                    title={`Sort by ${column.label.toLowerCase()}`}
                    onClick={() => {
                      const next = { key: column.key, direction: sort.key === column.key && sort.direction === "ascending" ? "descending" as const : "ascending" as const };
                      setSort(next);
                      setSortedFor(matchKey);
                      try { localStorage.setItem(sortStorageKey, JSON.stringify(next)); } catch { /* Keep the in-memory preference. */ }
                      anchor.current = null;
                    }}
                  >
                    {column.label}{!relevance && sort.key === column.key && <span aria-hidden="true">{sort.direction === "ascending" ? " ↑" : " ↓"}</span>}
                  </button>
                </th>
                {/* Behaviors sit beside the source so they stay in view; scores scroll if the table is wider than the page. */}
                {browse && column.key === "source" && <th scope="col" className="w-72 px-3 py-2 font-medium normal-case">Behaviors</th>}
                </Fragment>
              ))}
              {browse && <th className="w-10 px-2 py-2" />}
            </tr>
          </thead>
          <tbody>
            {groups.map((group, gi) => <Fragment key={group.session ? `session-${group.session}` : `rows-${gi}`}>
              {group.session && <tr className="h-7 border-b border-border-subtle bg-surface/40"><td colSpan={COLUMNS.length + 3} className="px-3 text-[11px] text-muted-foreground">Session <span className="font-mono">{group.session.slice(0, 8)}</span>, {group.rows.length} traces</td></tr>}
              {group.rows.map((trace) => <TraceRow
                key={trace.id}
                trace={trace}
                info={browse ? infoFor(trace.id) : undefined}
                query={matches?.query ?? ""}
                nested={!!group.session}
                mode={mode}
                checked={selected.has(trace.id)}
                onToggle={(e) => toggleRow(trace.id, e.shiftKey)}
                selectionDisabled={selectionDisabled || (mode === "browse" && trace.can_score === false)}
                deleting={deletingId === trace.id}
                onDelete={trace.can_score !== false && onDelete ? (() => onDelete(trace)) : undefined}
              />)}
            </Fragment>)}
          </tbody>
        </table>
        {visible.length === 0 && !searching && !searchError && !loadingMatches && (
          <p className="m-0 px-3 py-6 text-center text-[12.5px] text-muted-foreground">No traces match.</p>
        )}
      </div>
        <p className="m-0 mt-1.5 text-right text-[11px] text-muted-foreground tabular-nums">
          {searching ? "Searching…" : `${visible.length} trace${visible.length === 1 ? "" : "s"}${matches?.mode === "semantic" ? ", semantic" : matches?.mode === "text" ? ", text match" : ""}`}
        </p>
    </div>
  );
}

function TraceRow({
  trace,
  info,
  query,
  nested,
  mode,
  checked,
  onToggle,
  deleting,
  onDelete,
  selectionDisabled,
}: {
  trace: RmTraceSummary;
  /** Search match or behavior hits for this trace (browse only). */
  info?: SearchResult;
  query: string;
  nested: boolean;
  mode: "browse" | "picker";
  checked: boolean;
  onToggle: (e: MouseEvent) => void;
  selectionDisabled: boolean;
  deleting: boolean;
  onDelete: (() => void) | undefined;
}) {
  const picker = mode === "picker";
  const router = useRouter();
  const href = `/reward-models/traces/${trace.id}`;
  const segment = info?.segments[0];
  const quote = segment ? (segment.quote?.trim() || cleanSnippet(segment.snippet)) : "";

  function openRow(event: MouseEvent) {
    if ((event.target as Element).closest("a, button, input")) return;
    if (picker || event.shiftKey) {
      event.preventDefault();
      if (selectionDisabled) return;
      onToggle(event);
      return;
    }
    if (event.metaKey || event.ctrlKey) {
      window.open(href, "_blank", "noopener,noreferrer");
      return;
    }
    router.push(href);
  }

  return (
    <tr
      onClick={openRow}
      className={cn(
        "group cursor-pointer border-b border-border-subtle select-none last:border-b-0",
        picker ? "h-10" : "h-7 [&>td]:py-0",
        checked ? "bg-brand-500/[0.06] hover:bg-brand-500/10" : "hover:bg-surface/60",
      )}
    >
      <td className={cn("py-1.5 pl-3", nested && "border-l-2 border-l-border")} onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={checked} disabled={selectionDisabled} onClick={onToggle} label={`Select ${trace.title}`} />
      </td>
      <td className="px-3 py-1.5">
        {picker ? (
          <div className="truncate font-medium text-foreground">{trace.title}</div>
        ) : (
          <Link href={href} onClick={(e) => { if (e.shiftKey) { e.preventDefault(); e.stopPropagation(); if (!selectionDisabled) onToggle(e); } }} className="block truncate font-medium text-foreground hover:text-brand-600">
            {trace.title}
          </Link>
        )}
        {segment && quote && <p className="m-0 mb-1 line-clamp-2 text-[11px] text-muted-foreground"><QuoteSnippet text={quote} query={query} /> <Link href={traceStepHref(trace.id, segment.start_idx)} className="whitespace-nowrap text-[10.5px] text-brand-600 hover:underline">{stepWindow(segment.start_idx, segment.end_idx)}</Link></p>}
      </td>
      <td className="px-3 py-1.5 text-[12px] text-muted-foreground" title={`${traceSourceName(trace)}, Source ID: ${traceSourceId(trace)}`}><span className="block truncate">{traceSourceName(trace)}</span></td>
      {mode === "browse" && (
        <td className="px-3 py-1">
          {info && (info.outcome || info.behaviors.length > 0) && <div className="flex min-w-0 items-center gap-1 overflow-hidden whitespace-nowrap">
            {info.outcome && <OutcomeTag outcome={info.outcome} />}
            <BehaviorChips traceId={trace.id} behaviors={info.behaviors} max={2} className="min-w-0 flex-nowrap" />
          </div>}
        </td>
      )}
      <td className="px-3 py-1.5 text-right font-mono text-[12px] text-dim tabular-nums">{trace.step_count}</td>
      <td className="px-3 py-1.5 text-right font-mono text-[12px] text-dim tabular-nums">{trace.comment_count}</td>
      {[traceCredits(trace)?.mean, traceCredits(trace)?.min, traceCredits(trace)?.max].map((credit, i) => <td key={i} className="px-3 py-1.5 text-right font-mono text-[12px] tabular-nums" title="Automatic action annotation from −1 to +1">{credit == null ? "—" : (Math.round(credit * 100) / 100 || 0).toFixed(2)}</td>)}
      <td className="px-3 py-1.5 text-right" title={traceScoreLabel()}>
        {traceScore(trace) !== null ? <div className="leading-4"><span className="font-mono text-[12px] text-foreground tabular-nums">{traceScore(trace)!.toFixed(2)}</span></div> : <span className="text-muted-foreground">—</span>}
      </td>
      <td className="px-3 py-1.5 text-right text-[12px] whitespace-nowrap text-muted-foreground tabular-nums"><ImportTime value={trace.created_at} /></td>

      {mode === "browse" && (
        <td className="px-2 py-1.5 text-right">
          {onDelete && (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={onDelete}
              disabled={deleting || selectionDisabled}
              aria-label="Delete trace"
              className="opacity-0 group-hover:opacity-100 hover:text-red-600 disabled:opacity-100"
            >
              <Trash2 />
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}

function ImportTime({ value }: { value: string }) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return <span>—</span>;
  const format: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" };
  return <time dateTime={value} title={date.toLocaleString(undefined, { ...format, timeZoneName: "long" })}>{date.toLocaleString(undefined, format)}</time>;
}

function Checkbox({
  checked,
  indeterminate = false,
  onClick,
  label,
  disabled = false,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  onClick: (e: MouseEvent) => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    ref.current!.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={() => {}}
      onClick={onClick}
      aria-label={label}
      className="size-3.5 cursor-pointer accent-brand-500 disabled:cursor-default disabled:opacity-40"
    />
  );
}

export default function TraceTable(props: React.ComponentProps<typeof LatestTraceTable>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceTable {...props} />;
}
