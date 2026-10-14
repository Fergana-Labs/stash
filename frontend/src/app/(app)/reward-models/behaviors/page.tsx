"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Plus, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  ActorChip, BehaviorChip, ChangeLabel, EnabledSwitch, NewBehaviorDialog, SaveToEvalDialog, SeverityTag, Sparkline, type TraceWindow,
} from "@/components/behaviors/behavior-ui";
import {
  ACTORS, installStarters, getBehaviorOverview, listBehaviors, searchBehaviorTraces, stepWindow, traceStepHref, updateBehavior,
  type Actor, type BehaviorTrend, type SearchResponse, type SearchResult,
} from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";
import CohortsSection from "@/components/behaviors/CohortsSection";

const RANGES = [{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }];

/** The window a search row stands for: the best matching segment, else its first behavior hit, else the whole trace start. */
function resultWindow(r: SearchResult, filter: Set<string>): TraceWindow {
  const seg = r.segments[0];
  if (seg) return { trace_id: r.trace_id, start_idx: seg.start_idx, end_idx: seg.end_idx };
  const hit = r.behaviors.find((b) => filter.has(b.behavior_id)) ?? r.behaviors[0];
  if (hit) return { trace_id: r.trace_id, start_idx: hit.start_idx, end_idx: hit.end_idx };
  return { trace_id: r.trace_id, start_idx: 0, end_idx: 0 };
}

export default function BehaviorsPage() {
  useBreadcrumbs([{ label: "Behaviors" }], "behaviors");
  const [trends, setTrends] = useState<BehaviorTrend[] | null>(null);
  const [rules, setRules] = useState<string[]>([]);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [view, setView] = useState<"monitors" | "cohorts">("monitors");
  const [installing, setInstalling] = useState(false);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [overview, list] = await Promise.all([getBehaviorOverview(days), listBehaviors()]);
      setTrends(overview.behaviors);
      setRules(list.rules);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [days]);
  useEffect(() => { void load(); }, [load]);

  const filterKey = [...filter].sort().join(",");
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      setSearching(true);
      searchBehaviorTraces({ q: query, behaviors: filterKey ? filterKey.split(",") : [], days, limit: 50 })
        .then((r) => { if (!cancelled) { setSearch(r); setSearchError(""); setSelected(new Set()); } })
        .catch((e) => { if (!cancelled) setSearchError(errorMessage(e)); })
        .finally(() => { if (!cancelled) setSearching(false); });
    }, query.trim() ? 300 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, filterKey, days]);

  async function toggleEnabled(trend: BehaviorTrend, enabled: boolean) {
    setTrends((cur) => cur?.map((t) => t.behavior.id === trend.behavior.id ? { ...t, behavior: { ...t.behavior, enabled } } : t) ?? cur);
    try {
      await updateBehavior(trend.behavior.id, { enabled });
    } catch (e) {
      toast.error(errorMessage(e));
      void load();
    }
  }

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

  function toggleFilter(id: string) {
    setFilter((cur) => { const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }

  const results = search?.results ?? [];
  const windows = results.filter((r) => selected.has(r.trace_id)).map((r) => resultWindow(r, filter));
  const grouped = ACTORS.map((a) => ({ ...a, rows: trends?.filter((t) => t.behavior.actor === a.value) ?? [] })).filter((g) => g.rows.length);

  return <EvalPageFrame title="Behaviors" description="Named patterns Stash tags on your agents' traces: how often they happen, where, and whether they are getting worse."
    actions={<div className="flex gap-2">
      {trends && !trends.length && <Button size="sm" variant="outline" disabled={installing} onClick={() => void addStarters()}><Sparkles />{installing ? "Adding…" : "Add starter behaviors"}</Button>}
      <Button size="sm" onClick={() => setCreating(true)}><Plus />New behavior</Button>
    </div>}>
    {error && <p role="alert" className="mb-3 text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    <nav role="tablist" aria-label="Behaviors view" className="mb-4 flex gap-1 border-b border-border">
      {([["monitors", "Monitors & traces"], ["cohorts", "Cohorts"]] as const).map(([value, label]) => <button key={value} role="tab" type="button" aria-selected={view === value} onClick={() => setView(value)}
        className={cn("-mb-px border-b-2 px-3 py-2 text-[13px]", view === value ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</button>)}
    </nav>
    {view === "cohorts" ? <CohortsSection /> : <>

    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Monitors</h2>
      <Select aria-label="Time range" value={String(days)} onChange={(v) => setDays(Number(v))} options={RANGES} className="h-8 w-36 text-xs" />
    </div>
    <div className="mb-8 overflow-x-auto rounded border border-border"><table aria-label="Behaviors" className="w-full min-w-[720px] text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Behavior</th><th>Severity</th><th className="text-right">Last 7 days</th><th className="text-right">vs. prior week</th><th>Daily hits</th><th className="w-16 text-right">On</th></tr></thead>
      {grouped.map((g) => <tbody key={g.value}>
        <tr className="h-7 border-b border-border bg-surface/30"><td colSpan={6} className="px-3"><ActorChip actor={g.value as Actor} /></td></tr>
        {g.rows.map((t) => <tr key={t.behavior.id} className={cn("h-11 border-b border-border hover:bg-surface/60 [&>td]:px-3", !t.behavior.enabled && "opacity-60")}>
          <td><Link href={`/reward-models/behaviors/${t.behavior.id}`} className="font-medium hover:underline">{t.behavior.name}</Link></td>
          <td><SeverityTag severity={t.behavior.severity} /></td>
          <td className="text-right tabular-nums">{t.last_7_days}</td>
          <td className="text-right"><ChangeLabel change={t.change} current={t.last_7_days} /></td>
          <td><Sparkline series={t.series} /></td>
          <td className="text-right"><EnabledSwitch checked={t.behavior.enabled} label={`Monitor ${t.behavior.name}`} onChange={(v) => void toggleEnabled(t, v)} /></td>
        </tr>)}
      </tbody>)}
      {!trends && !error && <tbody><tr><td colSpan={6} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading behaviors…</span></td></tr></tbody>}
      {trends && !trends.length && <tbody><tr><td colSpan={6} className="px-3 py-8 text-muted-foreground">No behaviors yet. Add the starter set (frustration, tool errors, repeated calls…) or define your own.</td></tr></tbody>}
    </table></div>

    <h2 className="mb-3 text-sm font-semibold">Traces</h2>
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <label className="flex h-8 w-80 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Filter traces" placeholder="Filter traces…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label>
      {trends?.map((t) => <button key={t.behavior.id} type="button" aria-pressed={filter.has(t.behavior.id)} onClick={() => toggleFilter(t.behavior.id)}
        className={cn("rounded-full border px-2 py-0.5 text-[11px] transition-colors", filter.has(t.behavior.id) ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground")}>{t.behavior.name}</button>)}
      <span className="ml-auto text-xs text-muted-foreground">{searching ? "Searching…" : search ? `${results.length} traces${search.mode === "semantic" ? " · semantic" : search.mode === "text" ? " · text match" : ""}` : ""}</span>
    </div>
    {selected.size > 0 && <div className="mb-2 flex items-center gap-3 rounded border border-border bg-surface/40 px-3 py-1.5 text-xs">
      <span>{selected.size} selected</span>
      <Button size="xs" onClick={() => setSaving(true)}>Save to eval</Button>
      <button className="text-muted-foreground hover:text-foreground" onClick={() => setSelected(new Set())}>Clear</button>
    </div>}
    {searchError && <p role="alert" className="mb-2 text-xs text-destructive">{searchError}</p>}
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Traces" className="w-full min-w-[900px] table-fixed text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium">
        <th className="w-8"><input type="checkbox" aria-label="Select all" checked={results.length > 0 && selected.size === results.length} onChange={(e) => setSelected(e.target.checked ? new Set(results.map((r) => r.trace_id)) : new Set())} /></th>
        <th className="w-36">Timestamp</th><th className="w-32">Agent</th><th>Input</th><th>Output</th><th className="w-64">Behaviors</th>
      </tr></thead>
      <tbody>
        {results.map((r) => {
          const win = resultWindow(r, filter);
          return <tr key={r.trace_id} className={cn("border-b border-border align-top hover:bg-surface/60 [&>td]:px-3 [&>td]:py-2", selected.has(r.trace_id) && "bg-surface/60")}>
            <td><input type="checkbox" aria-label={`Select ${r.title ?? "trace"}`} checked={selected.has(r.trace_id)} onChange={() => setSelected((cur) => { const next = new Set(cur); if (next.has(r.trace_id)) next.delete(r.trace_id); else next.add(r.trace_id); return next; })} /></td>
            <td className="tabular-nums text-muted-foreground"><Link href={traceStepHref(r.trace_id, win.start_idx)} className="hover:text-foreground hover:underline">{new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Link></td>
            <td className="truncate">{r.agent ?? "—"}</td>
            <td><Link href={traceStepHref(r.trace_id, win.start_idx)} className="line-clamp-2 hover:underline" title={r.title ?? undefined}>{r.input || r.title || "—"}</Link>
              {r.segments[0] && <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground"><span className="font-medium">{stepWindow(r.segments[0].start_idx, r.segments[0].end_idx)}:</span> {r.segments[0].snippet}</p>}</td>
            <td><span className="line-clamp-3 text-muted-foreground">{r.output || "—"}</span></td>
            <td><div className="flex flex-wrap gap-1">{r.behaviors.map((b) => <Link key={b.id} href={traceStepHref(r.trace_id, b.start_idx)} title={stepWindow(b.start_idx, b.end_idx)}><BehaviorChip name={b.name} actor={b.actor} /></Link>)}</div></td>
          </tr>;
        })}
        {search && !results.length && !searching && <tr><td colSpan={6} className="px-3 py-8 text-muted-foreground">{query.trim() || filter.size ? "No traces match." : "No traces in this time range."}</td></tr>}
        {!search && !searchError && <tr><td colSpan={6} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading traces…</span></td></tr>}
      </tbody>
    </table></div>

    </>}
    <NewBehaviorDialog open={creating} onOpenChange={setCreating} rules={rules} onCreated={() => void load()} />
    <SaveToEvalDialog open={saving} onOpenChange={setSaving} windows={windows} onSaved={() => setSelected(new Set())} />
  </EvalPageFrame>;
}
