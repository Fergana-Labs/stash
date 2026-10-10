"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceTable";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Search, Trash2 } from "lucide-react";
import { Select } from "@/components/ui/select";
import { rmListAllTraces } from "@/lib/api";
import { traceScore, traceScoreLabel, traceCredits } from "./trace-metrics";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmTraceSummary } from "@/lib/types";
import { selectRange, sortTraces, toggleAllVisible, type TraceSortKey, type TraceSortDirection } from "./trace-selection";
import { matchesTraceFilters, traceSourceId, traceSourceKey, traceSourceName, type TraceFilters } from "./trace-sources";
import TraceSourceNameDialog from "./TraceSourceNameDialog";

const COLUMNS: { key: TraceSortKey; label: string; className: string }[] = [
  { key: "title", label: "Trace", className: "" },
  { key: "source", label: "Source", className: "w-36" },
  { key: "steps", label: "Steps", className: "w-16 text-right" },
  { key: "comments", label: "Comments", className: "w-24 text-right" },
  { key: "credit", label: "Avg. credit", className: "w-24 text-right" },
  { key: "minCredit", label: "Min. credit", className: "w-24 text-right" },
  { key: "maxCredit", label: "Max. credit", className: "w-24 text-right" },
  { key: "reward", label: "Trace score", className: "w-28 text-right" },
  { key: "imported", label: "Imported", className: "w-52 text-right" },
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
}: {
  traces: RmTraceSummary[];
  selected: Set<string>;
  onSelectedChange: (next: Set<string>) => void;
  mode: "browse" | "picker";
  onDelete?: (trace: RmTraceSummary) => void;
  deletingId?: string | null;
  selectionDisabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("all");
  const [filters, setFilters] = useState<TraceFilters>({ source: "all", from: "", through: "" });
  const [sourceNames, setSourceNames] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<{ key: TraceSortKey; direction: TraceSortDirection }>({ key: "imported", direction: "descending" });
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
  const searching = !!query.trim() && searchResults === null && !searchError;
  const namedTrace = (trace: RmTraceSummary) => sourceNames[traceSourceKey(trace)]
    ? { ...trace, source_name: sourceNames[traceSourceKey(trace)] } : trace;
  const sources = Array.from(new Map(traces.map((trace) => [traceSourceKey(trace), namedTrace(trace)])).values())
    .sort((a, b) => traceSourceName(a).localeCompare(traceSourceName(b)));
  const selectedSource = sources.find((trace) => traceSourceKey(trace) === filters.source);
  // Search can return traces shared for review; only the loaded picker set is trainable.
  const selectableIds = new Set(traces.map((trace) => trace.id));
  const filtered = (query.trim() ? searchResults ?? [] : traces).map(namedTrace)
    .filter((trace) => (mode !== "picker" || selectableIds.has(trace.id)) && matchesTraceFilters(trace, filters))
    .filter((trace) => assessmentFilter === "all"
    || (assessmentFilter === "scored" && traceScore(trace) !== null)
    || (assessmentFilter === "unscored" && traceScore(trace) === null));
  const visible = sortTraces(filtered, sort.key, sort.direction, "automatic");
  const visibleIds = visible.filter((t) => mode === "picker" || t.can_score !== false).map((t) => t.id);
  const selectedVisible = visibleIds.filter((id) => selected.has(id)).length;
  const hiddenSelected = traces.filter((trace) => selected.has(trace.id)).length - selectedVisible;
  const hasFilters = filters.source !== "all" || !!filters.from || !!filters.through;
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
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {mode === "picker" && <label className="flex h-7 w-64 items-center gap-1.5 rounded-md border border-border bg-background px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20">
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
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>}
        {mode === "browse" && <Select aria-label="Filter traces" value={assessmentFilter} onChange={(value) => { setAssessmentFilter(value); anchor.current = null; }} className="h-7 min-w-32 px-2 text-[12px]" options={[{ value: "all", label: "All traces" }, { value: "scored", label: "Scored" }, { value: "unscored", label: "Unscored" }]} />}
        <div className="flex items-center gap-1">
          <Select aria-label="Filter by source" value={filters.source} onChange={(source) => changeFilters({ source })} className="h-7 max-w-60 min-w-36 px-2 text-[12px]" options={[
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
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
          <span>Imported</span>
          <input type="date" aria-label="Imported from" value={filters.from} max={filters.through || undefined} onChange={(e) => changeFilters({ from: e.target.value })} className="h-7 rounded-md border border-border bg-background px-2 text-foreground" />
          <span>to</span>
          <input type="date" aria-label="Imported through" value={filters.through} min={filters.from || undefined} onChange={(e) => changeFilters({ through: e.target.value })} className="h-7 rounded-md border border-border bg-background px-2 text-foreground" />
          {hasFilters && <Button variant="ghost" size="xs" onClick={() => changeFilters({ source: "all", from: "", through: "" })}>Clear filters</Button>}
        </div>

        <span className="ml-auto text-[12px] text-muted-foreground tabular-nums">
          {searching ? "Searching…" : `${visible.length} traces`}
        </span>
      </div>

      {(mode === "picker" || selected.size > 0) && <div className="mb-3 flex items-center gap-3 text-[12px] text-muted-foreground">
        <Button variant="outline" size="xs" disabled={selectionDisabled || searching || !!searchError || visibleIds.length === 0} onClick={() => { onSelectedChange(new Set(visibleIds)); anchor.current = null; }}>Select only shown</Button>
        <span>{selectedVisible} shown selected{hiddenSelected > 0 && ` · ${hiddenSelected} selected outside these filters`}</span>
      </div>}
      {invalidDates && <p role="alert" className="mb-3 text-xs text-red-600">The end date must be on or after the start date.</p>}
      {searchError && <p role="alert" className="mb-3 text-sm text-red-600">{searchError}</p>}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[1140px] table-fixed border-collapse text-[13px]">
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
                <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction : "none"} className={cn("px-3 py-2 font-medium", column.className)}>
                  <button
                    type="button"
                    className="cursor-pointer whitespace-nowrap hover:text-foreground"
                    title={`Sort by ${column.label.toLowerCase()}`}
                    onClick={() => {
                      const next = { key: column.key, direction: sort.key === column.key && sort.direction === "ascending" ? "descending" as const : "ascending" as const };
                      setSort(next);
                      try { localStorage.setItem(sortStorageKey, JSON.stringify(next)); } catch { /* Keep the in-memory preference. */ }
                      anchor.current = null;
                    }}
                  >
                    {column.label}{sort.key === column.key && <span aria-hidden="true">{sort.direction === "ascending" ? " ↑" : " ↓"}</span>}
                  </button>
                </th>
              ))}
              {mode === "browse" && <th className="w-10 px-2 py-2" />}
            </tr>
          </thead>
          <tbody>
            {visible.map((trace) => (
              <TraceRow
                key={trace.id}
                trace={trace}
                mode={mode}
                checked={selected.has(trace.id)}
                onToggle={(e) => toggleRow(trace.id, e.shiftKey)}
                selectionDisabled={selectionDisabled || (mode === "browse" && trace.can_score === false)}
                deleting={deletingId === trace.id}
                onDelete={trace.can_score !== false && onDelete ? (() => onDelete(trace)) : undefined}
              />
            ))}
          </tbody>
        </table>
        {visible.length === 0 && !searching && !searchError && (
          <p className="m-0 px-3 py-6 text-center text-[12.5px] text-muted-foreground">No traces match.</p>
        )}
      </div>
    </div>
  );
}

function TraceRow({
  trace,
  mode,
  checked,
  onToggle,
  deleting,
  onDelete,
  selectionDisabled,
}: {
  trace: RmTraceSummary;
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
      <td className="py-1.5 pl-3" onClick={(e) => e.stopPropagation()}>
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
      </td>
      <td className="px-3 py-1.5 text-[12px] text-muted-foreground" title={`${traceSourceName(trace)} · Source ID: ${traceSourceId(trace)}`}><span className="block truncate">{traceSourceName(trace)}</span></td>
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
