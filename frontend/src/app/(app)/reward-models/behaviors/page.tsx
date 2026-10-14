"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Flag, Plus, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  ActorChip, BehaviorChips, BehaviorMultiSelect, ChangeLabel, NewBehaviorDialog, OutcomeTag, QuoteSnippet, ReleaseDialog, SaveToEvalDialog, SeverityDot, Sparkline,
  cleanSnippet, groupBySession, type TraceWindow,
} from "@/components/behaviors/behavior-ui";
import {
  ACTORS, COHORT_DIMENSIONS, installStarters, getBehaviorOverview, searchBehaviorTraces, stepWindow, traceStepHref,
  type Actor, type BehaviorTrend, type CohortBy, type SearchResponse, type SearchResult,
} from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";
import CohortsSection from "@/components/behaviors/CohortsSection";

const RANGES = [{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }];
const GROUP_BY = [{ value: "none", label: "None" }, ...COHORT_DIMENSIONS];

/** The window a search row stands for: the best matching segment, else its first behavior hit, else the whole trace start. */
function resultWindow(r: SearchResult, filter: Set<string>): TraceWindow {
  const seg = r.segments[0];
  if (seg) return { trace_id: r.trace_id, start_idx: seg.start_idx, end_idx: seg.end_idx };
  const hit = r.behaviors.find((b) => filter.has(b.behavior_id)) ?? r.behaviors[0];
  if (hit) return { trace_id: r.trace_id, start_idx: hit.start_idx, end_idx: hit.end_idx };
  return { trace_id: r.trace_id, start_idx: 0, end_idx: 0 };
}

const when = (s: string) => new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export default function BehaviorsPage() {
  useBreadcrumbs([{ label: "Behaviors" }], "behaviors");
  const [trends, setTrends] = useState<BehaviorTrend[] | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [marking, setMarking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [groupBy, setGroupBy] = useState<CohortBy | "none">("none");

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setTrends((await getBehaviorOverview(days)).behaviors);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [days]);
  useEffect(() => { void load(); }, [load]);

  const filterKey = [...filter].sort().join(",");
  useEffect(() => {
    if (groupBy !== "none") return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setSearching(true);
      searchBehaviorTraces({ q: query, behaviors: filterKey ? filterKey.split(",") : [], days, limit: 50 })
        .then((r) => { if (!cancelled) { setSearch(r); setSearchError(""); setSelected(new Set()); } })
        .catch((e) => { if (!cancelled) setSearchError(errorMessage(e)); })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, query.trim() ? 300 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, filterKey, days, groupBy]);

  async function addStarters() {
    setInstalling(true);
    try {
      const { created } = await installStarters();
      toast.success(`Added ${created.length} starter behavior${created.length === 1 ? "" : "s"}`);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setInstalling(false);
    }
  }

  const results = search?.results ?? [];
  const windows = results.filter((r) => selected.has(r.trace_id)).map((r) => resultWindow(r, filter));
  const grouped = ACTORS.map((a) => ({ ...a, rows: trends?.filter((t) => t.behavior.actor === a.value) ?? [] })).filter((g) => g.rows.length);
  // Week-over-week change is noise until there is a prior week to compare with.
  const showChange = !!trends?.some((t) => t.previous_7_days > 0);
  const columns = showChange ? 4 : 3;
  const agents = [...new Set(results.map((r) => r.agent).filter((a): a is string => !!a))].sort();
  const toggle = (id: string) => setSelected((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next; });

  function row(r: SearchResult, nested: boolean) {
    const win = resultWindow(r, filter);
    const seg = r.segments[0];
    const quote = seg ? (seg.quote?.trim() || cleanSnippet(seg.snippet)) : "";
    return <tr key={r.trace_id} className={cn("border-b border-border align-top hover:bg-surface/60 [&>td]:px-3 [&>td]:py-2", selected.has(r.trace_id) && "bg-surface/60")}>
      <td className={cn(nested && "border-l-2 border-l-border")}><input type="checkbox" aria-label={`Select ${r.title ?? "trace"}`} checked={selected.has(r.trace_id)} onChange={() => toggle(r.trace_id)} /></td>
      <td className="tabular-nums text-muted-foreground"><Link href={traceStepHref(r.trace_id, win.start_idx)} className="hover:text-foreground hover:underline">{when(r.created_at)}</Link></td>
      <td className="truncate">{r.agent ?? "—"}</td>
      <td><Link href={traceStepHref(r.trace_id, win.start_idx)} className="line-clamp-2 hover:underline" title={r.title ?? undefined}>{r.input || r.title || "—"}</Link>
        {seg && quote && <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground"><QuoteSnippet text={quote} query={query} /> <Link href={traceStepHref(r.trace_id, seg.start_idx)} className="whitespace-nowrap text-[10.5px] text-brand-600 hover:underline">{stepWindow(seg.start_idx, seg.end_idx)}</Link></p>}</td>
      <td><span className="line-clamp-3 text-muted-foreground">{r.final_output || r.output || "—"}</span>{r.outcome && <div className="mt-1"><OutcomeTag outcome={r.outcome} /></div>}</td>
      <td><BehaviorChips traceId={r.trace_id} behaviors={r.behaviors} /></td>
    </tr>;
  }

  return <EvalPageFrame title="Behaviors" description="Named patterns Stash tags on your agents' traces: how often they happen, where, and whether they are getting worse."
    actions={<div className="flex gap-2">
      {trends && !trends.length && <Button size="sm" variant="outline" disabled={installing} onClick={() => void addStarters()}><Sparkles />{installing ? "Adding…" : "Add starter behaviors"}</Button>}
      <Button size="sm" variant="outline" onClick={() => setMarking(true)}><Flag />Add release marker</Button>
      <Button size="sm" onClick={() => setCreating(true)}><Plus />New behavior</Button>
    </div>}>
    {error && <p role="alert" className="mb-3 text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}

    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Monitors</h2>
      <Select aria-label="Time range" value={String(days)} onChange={(v) => setDays(Number(v))} options={RANGES} className="h-8 w-36 text-xs" />
    </div>
    <div className="mb-8 overflow-x-auto rounded border border-border"><table aria-label="Behaviors" className="w-full min-w-[560px] text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Behavior</th><th className="text-right">Last 7 days</th>{showChange && <th className="text-right">vs. prior week</th>}<th className="w-32">Daily hits</th></tr></thead>
      {grouped.map((g) => <tbody key={g.value}>
        <tr className="h-7 border-b border-border bg-surface/30"><td colSpan={columns} className="px-3"><ActorChip actor={g.value as Actor} /></td></tr>
        {g.rows.map((t) => <tr key={t.behavior.id} className="h-11 border-b border-border hover:bg-surface/60 [&>td]:px-3">
          <td><SeverityDot severity={t.behavior.severity} /><Link href={`/reward-models/behaviors/${t.behavior.id}`} className={cn("font-medium hover:underline", !t.behavior.enabled && "text-muted-foreground")}>{t.behavior.name}</Link>{!t.behavior.enabled && <span className="ml-2 text-[11px] text-muted-foreground/70">Off</span>}</td>
          <td className="text-right tabular-nums">{t.last_7_days}</td>
          {showChange && <td className="text-right"><ChangeLabel change={t.change} current={t.last_7_days} /></td>}
          <td><Sparkline series={t.series} className={cn(!t.behavior.enabled && "opacity-40")} /></td>
        </tr>)}
      </tbody>)}
      {!trends && !error && <tbody><tr><td colSpan={columns} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading behaviors…</span></td></tr></tbody>}
      {trends && !trends.length && <tbody><tr><td colSpan={columns} className="px-3 py-8 text-muted-foreground">No behaviors yet. Add the starter set (frustration, tool errors, repeated calls…) or define your own.</td></tr></tbody>}
    </table></div>

    <h2 className="mb-3 text-sm font-semibold">Traces</h2>
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {groupBy === "none" && <label className="flex h-8 w-80 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Filter traces" placeholder="Filter traces…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label>}
      {groupBy === "none" && <BehaviorMultiSelect behaviors={trends?.map((t) => t.behavior) ?? []} selected={filter} onChange={setFilter} />}
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">Group by<Select aria-label="Group by" value={groupBy} onChange={(v) => setGroupBy(v as CohortBy | "none")} options={GROUP_BY} className="h-8 w-36 text-xs text-foreground" /></span>
      {groupBy === "none" && <span className="ml-auto text-xs text-muted-foreground">{searching ? "Searching…" : search ? `${results.length} traces${search.mode === "semantic" ? " · semantic" : search.mode === "text" ? " · text match" : ""}` : ""}</span>}
    </div>
    {groupBy !== "none" ? <CohortsSection by={groupBy} days={days} /> : <>
      {selected.size > 0 && <div className="mb-2 flex items-center gap-3 rounded border border-border bg-surface/40 px-3 py-1.5 text-xs">
        <span>{selected.size} selected</span>
        <Button size="xs" onClick={() => setSaving(true)}>Add to eval</Button>
        <button className="text-muted-foreground hover:text-foreground" onClick={() => setSelected(new Set())}>Clear</button>
      </div>}
      {searchError && <p role="alert" className="mb-2 text-xs text-destructive">{searchError}</p>}
      <div className="overflow-x-auto rounded border border-border"><table aria-label="Traces" className="w-full min-w-[900px] table-fixed text-left text-xs">
        <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium">
          <th className="w-8"><input type="checkbox" aria-label="Select all" checked={results.length > 0 && selected.size === results.length} onChange={(e) => setSelected(e.target.checked ? new Set(results.map((r) => r.trace_id)) : new Set())} /></th>
          <th className="w-32">Timestamp</th><th className="w-28">Agent</th><th>Input</th><th>Output</th><th className="w-60">Behaviors</th>
        </tr></thead>
        <tbody>
          {groupBySession(results).map((g) => g.session === null ? row(g.rows[0], false) : <Fragment key={`session-${g.session}`}>
            <tr className="h-7 border-b border-border bg-surface/30"><td colSpan={6} className="px-3 text-[11px] text-muted-foreground">Session <span className="font-mono">{g.session.slice(0, 8)}</span> · {g.rows.length} traces</td></tr>
            {g.rows.map((r) => row(r, true))}
          </Fragment>)}
          {search && !results.length && !searching && <tr><td colSpan={6} className="px-3 py-8 text-muted-foreground">{query.trim() || filter.size ? "No traces match." : "No traces in this time range."}</td></tr>}
          {!search && !searchError && <tr><td colSpan={6} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading traces…</span></td></tr>}
        </tbody>
      </table></div>
    </>}
    <NewBehaviorDialog open={creating} onOpenChange={setCreating} onCreated={() => void load()} />
    <ReleaseDialog open={marking} onOpenChange={setMarking} agents={agents} onCreated={() => undefined} />
    <SaveToEvalDialog open={saving} onOpenChange={setSaving} windows={windows} onSaved={() => setSelected(new Set())} />
  </EvalPageFrame>;
}
