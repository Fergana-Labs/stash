"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TracesPage";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import ImportTracesDialog from "@/components/reward-models/ImportTracesDialog";
import ConnectAgentDialog from "@/components/reward-models/ConnectAgentDialog";
import TraceDropzone from "@/components/reward-models/TraceDropzone";
import TraceTable, { type TraceMatches } from "@/components/reward-models/TraceTable";
import { Select } from "@/components/ui/select";
import MonitorsSection from "@/components/behaviors/MonitorsSection";
import CohortsSection from "@/components/behaviors/CohortsSection";
import { BehaviorMultiSelect, SaveToEvalDialog, searchResultWindow, type TraceWindow } from "@/components/behaviors/behavior-ui";
import { COHORT_DIMENSIONS, getBehaviorOverview, searchBehaviorTraces, type BehaviorTrend, type CohortBy, type SearchResponse, type SearchResult } from "@/lib/behaviors-api";
import { RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { RmListSkeleton, RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { SELECTED_PARAM, summarizeSelection } from "@/components/reward-models/trace-selection";
import { rmDeleteTrace, rmListAllTraces } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";

// New runs stream in over OpenTelemetry, so the list refreshes itself.
const POLL_MS = 5000;
const DAY_MS = 86_400_000;
const RANGES = [{ value: "all", label: "All time" }, { value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }];
const GROUP_BY = [{ value: "none", label: "None" }, ...COHORT_DIMENSIONS];
// The behaviors search caps a page at 100 rows; that page also supplies behavior chips for the plain list.
const SEARCH_LIMIT = 100;

function LatestTracesPage() {
  return (
    <Suspense fallback={<RmPageSkeleton />}>
      <Traces />
    </Suspense>
  );
}

function Traces() {
  useBreadcrumbs([{ label: "Traces" }], "reward-models");
  const searchParams = useSearchParams();
  const confirm = useConfirm();
  const [traces, setTraces] = useState<RmTraceSummary[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(searchParams.get(SELECTED_PARAM)?.split(",").filter((id) => id !== "") ?? []),
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  // Background refresh runs only after a successful load. A failure stops it,
  // so a down backend shows one toast instead of one every POLL_MS; the next
  // successful load (page visit, import, delete) turns it back on.
  const [polling, setPolling] = useState(false);

  const [range, setRange] = useState("all");
  const [groupBy, setGroupBy] = useState<CohortBy | "none">("none");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Set<string>>(() => new Set(searchParams.getAll("behavior")));
  const [search, setSearch] = useState<{ key: string; response: SearchResponse } | null>(null);
  const [searchError, setSearchError] = useState("");
  const [trends, setTrends] = useState<BehaviorTrend[] | null>(null);
  const [trendsError, setTrendsError] = useState("");
  const [saving, setSaving] = useState(false);
  const days = range === "all" ? null : Number(range);

  const load = useCallback(async () => {
    try {
      setTraces(await rmListAllTraces());
      setPolling(true);
    } catch (e) {
      setPolling(false);
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  // Monitors show daily hits; "All time" charts the last 30 days.
  const overviewDays = days ?? 30;
  const loadTrends = useCallback(async () => {
    try {
      setTrends((await getBehaviorOverview(overviewDays)).behaviors);
      setTrendsError("");
    } catch (e) {
      setTrendsError(errorMessage(e));
    }
  }, [overviewDays]);
  useEffect(() => { void loadTrends(); }, [loadTrends]);

  // With a query or behavior filter the table shows search results; otherwise the same
  // endpoint's browse page supplies behavior chips and outcomes for the newest traces.
  const filterKey = [...filter].sort().join(",");
  const searchDays = days ?? 365;
  const searchKey = `${query.trim()}|${filterKey}|${searchDays}`;
  const searchActive = !!query.trim() || filter.size > 0;
  const traceCount = traces?.length ?? 0;
  useEffect(() => {
    if (groupBy !== "none") return;
    let cancelled = false;
    const timer = setTimeout(() => {
      // Similarity alone ranks every trace, matching or not; the rerank keeps only real matches.
      searchBehaviorTraces({ q: query, behaviors: filterKey ? filterKey.split(",") : [], days: searchDays, limit: SEARCH_LIMIT, rerank: !!query.trim() })
        .then((response) => { if (!cancelled) { setSearch({ key: searchKey, response }); setSearchError(""); } })
        .catch((e) => { if (!cancelled) setSearchError(errorMessage(e)); });
    }, query.trim() ? 600 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, filterKey, searchDays, searchKey, groupBy, traceCount]);

  const current = search?.key === searchKey ? search.response : null;
  const matches: TraceMatches | null = searchActive
    ? { results: current?.results ?? [], mode: current?.mode ?? null, query, behaviors: filterKey ? filterKey.split(",") : [], loading: !current && !searchError }
    : null;
  const behaviorsByTrace = useMemo(
    () => new Map((search?.response.results ?? []).map((r) => [r.trace_id, r] as [string, SearchResult])),
    [search],
  );
  const agents = [...new Set([...(traces ?? []).map((t) => t.agent), ...(search?.response.results ?? []).map((r) => r.agent)]
    .filter((a): a is string => !!a))].sort();
  const focusedId = filter.size === 1 ? [...filter][0] : null;
  const shownTraces = days === null || !traces ? traces : traces.filter((t) => Date.parse(t.created_at) >= Date.now() - days * DAY_MS);

  async function remove(targets: RmTraceSummary[]) {
    if (!targets.length || deleting) return;
    const ok = await confirm({
      title: targets.length === 1 ? `Delete "${targets[0].title}"?` : `Delete ${targets.length} traces?`,
      body: "Their steps, annotations, and scores will be deleted. This cannot be undone.",
      confirmLabel: targets.length === 1 ? "Delete" : `Delete ${targets.length} traces`,
    });
    if (!ok) return;
    setDeleting(targets.length === 1 ? targets[0].id : "bulk");
    const removed = new Set<string>();
    const failed = new Set<string>();
    try {
      // Bound concurrent requests and keep failed selections available for retry.
      for (let i = 0; i < targets.length; i += 5) {
        const batch = targets.slice(i, i + 5);
        const results = await Promise.allSettled(batch.map((trace) => rmDeleteTrace(trace.id)));
        results.forEach((result, index) => {
          if (result.status === "fulfilled") removed.add(batch[index].id);
          else failed.add(batch[index].id);
        });
      }
      setSelected((previous) => new Set([...previous, ...failed].filter((id) => !removed.has(id))));
      setTraces((previous) => previous?.filter((trace) => !removed.has(trace.id)) ?? null);
      if (removed.size) toast.success(`Deleted ${removed.size} trace${removed.size === 1 ? "" : "s"}`);
      if (failed.size) toast.error(`Couldn’t delete ${failed.size} trace${failed.size === 1 ? "" : "s"}. They remain selected so you can try again.`);
      await load();
    } finally {
      setDeleting(null);
    }
  }

  // Only ids that still exist count: a deleted trace from ?selected= must not be sent to training.
  const deletable = (traces ?? []).filter((t) => selected.has(t.id) && t.can_score !== false);
  const summary = summarizeSelection(traces ?? [], selected);
  // A selected search row exports its matching window; a plain row exports the whole trace.
  const windows: TraceWindow[] = [...selected].flatMap((id) => {
    const hit = behaviorsByTrace.get(id);
    if (hit && (searchActive || hit.behaviors.length)) return [searchResultWindow(hit, filter)];
    const trace = traces?.find((t) => t.id === id);
    return trace ? [{ trace_id: id, start_idx: 0, end_idx: Math.max(0, trace.step_count - 1) }] : [];
  });

  const controls = <>
    {groupBy === "none" && <><label className="flex h-7 w-72 items-center gap-1.5 rounded-md border border-border bg-background px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20">
      <Search className="size-3.5 text-muted-foreground" />
      <input aria-label="Search traces" placeholder="Search traces by what happened…" value={query} onChange={(e) => setQuery(e.target.value)}
        className="min-w-0 flex-1 bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground" />
    </label>
    <BehaviorMultiSelect behaviors={trends?.map((t) => t.behavior) ?? []} selected={filter} onChange={setFilter} /></>}
    <Select aria-label="Time range" value={range} onChange={setRange} options={RANGES} className="h-7 w-32 px-2 text-[12px]" />
    <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">Group by<Select aria-label="Group by" value={groupBy} onChange={(v) => setGroupBy(v as CohortBy | "none")} options={GROUP_BY} className="h-7 w-32 px-2 text-[12px] text-foreground" /></span>
  </>;

  return (
    <TraceDropzone onImported={() => void load()}>
      <RmPage
        wide
        title="Traces"
        description="Your agents’ production traces, and the behaviors Stash watches for in them."
        actions={(
          <>
            <ConnectAgentDialog />
            <ImportTracesDialog onImported={() => void load()} />
          </>
        )}
      >
        <MonitorsSection
          trends={trends}
          error={trendsError}
          onReload={() => void loadTrends()}
          focusedId={focusedId}
          onFocus={(id) => setFilter(new Set(id ? [id] : []))}
          agents={agents}
        />
        {traces === null ? (
          <RmListSkeleton />
        ) : traces.length === 0 ? (
          <div className="py-24 text-center">
            <p className="m-0 text-[16px] font-medium text-foreground">Drop trace files or folders anywhere here</p>
            <p className="m-0 mt-2 text-[13px] text-muted-foreground">JSON, JSONL, or NDJSON. Or connect your agent to send runs automatically.</p>
          </div>
        ) : (
          <>
            {summary.count > 0 && (
              <div className="sticky top-0 z-20 -mx-3 mb-3 flex items-center gap-3 rounded-lg border border-brand-500/25 bg-background/95 px-3 py-2 shadow-sm backdrop-blur">
                <span className="text-[13px] font-medium text-foreground tabular-nums">
                  {summary.count} trace{summary.count === 1 ? "" : "s"} selected
                </span>
                <Button variant="ghost" size="sm" disabled={!!deleting} onClick={() => setSelected(new Set())}>
                  Clear
                </Button>
                <Button variant="outline" size="sm" disabled={!!deleting || windows.length === 0} onClick={() => setSaving(true)}>
                  Add to eval
                </Button>
                <Button variant="destructive" size="sm" disabled={!!deleting || deletable.length === 0} onClick={() => void remove(deletable)}>
                  {deleting ? "Deleting…" : "Delete selected"}
                </Button>
              </div>
            )}
            {searchError && groupBy === "none" && <p role="alert" className="mb-2 text-xs text-destructive">{searchError}</p>}
            {groupBy !== "none" ? <>
              <div className="mb-3 flex flex-wrap items-center gap-3">{controls}</div>
              <CohortsSection by={groupBy} days={overviewDays} />
            </> : <TraceTable
              traces={shownTraces ?? []}
              selected={selected}
              onSelectedChange={setSelected}
              mode="browse"
              onDelete={(t) => void remove([t])}
              selectionDisabled={!!deleting}
              deletingId={deleting}
              toolbar={controls}
              matches={matches}
              behaviorsByTrace={behaviorsByTrace}
            />}
            <SaveToEvalDialog open={saving} onOpenChange={setSaving} windows={windows} onSaved={() => setSelected(new Set())} />
          </>
        )}
      </RmPage>
    </TraceDropzone>
  );
}

export default function TracesPage() {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent />
    : <LatestTracesPage />;
}
