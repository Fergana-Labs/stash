"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight, ChevronDown, ChevronRight, Flag, Plus, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { traceActionClass } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { HitsChart, NewBehaviorDialog, ReleaseDialog, SeverityDot, SeverityTag, Sparkline, dailyBuckets } from "@/components/behaviors/behavior-ui";
import { ACTOR_COLOR, ACTORS, DETECTOR_LABEL, installStarters, listReleases, type BehaviorTrend, type Release } from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";

const COLLAPSED_KEY = "stash-traces-monitors-collapsed";
const actorOrder = (t: BehaviorTrend) => ACTORS.findIndex((a) => a.value === t.behavior.actor);

/**
 * The behaviors Stash watches for, as a compact strip above the trace table.
 * Clicking one filters the table to it and shows its hits over time.
 */
export default function MonitorsSection({ trends, error, onReload, focusedId, onFocus, agents, actions }: {
  trends: BehaviorTrend[] | null;
  error: string;
  onReload: () => void;
  focusedId: string | null;
  onFocus: (id: string | null) => void;
  agents: string[];
  actions?: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [marking, setMarking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [releases, setReleases] = useState<Release[]>([]);

  useEffect(() => {
    try { setCollapsed(localStorage.getItem(COLLAPSED_KEY) === "1"); } catch { /* Expanded by default without storage. */ }
  }, []);
  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0"); } catch { /* Keep the in-memory state. */ }
  }

  const loadReleases = useCallback(() => {
    // Release markers are an overlay on the chart; the strip works without them.
    listReleases().then((r) => setReleases(r.releases)).catch(() => setReleases([]));
  }, []);
  useEffect(() => { loadReleases(); }, [loadReleases]);

  async function addStarters() {
    setInstalling(true);
    try {
      const { created } = await installStarters();
      toast.success(`Added ${created.length} starter behavior${created.length === 1 ? "" : "s"}`);
      onReload();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setInstalling(false);
    }
  }

  const sorted = [...(trends ?? [])].sort((a, b) => actorOrder(a) - actorOrder(b));
  const focused = sorted.find((t) => t.behavior.id === focusedId) ?? null;

  return <section aria-label="Monitors" className="mb-2">
    <header className="mb-2 flex flex-wrap items-center gap-2">
      <button type="button" onClick={toggleCollapsed} aria-expanded={!collapsed} className="inline-flex items-center gap-1 text-[13px] font-semibold text-foreground">
        {collapsed ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}Monitors
        {trends && <span className="font-normal text-muted-foreground tabular-nums">{trends.length}</span>}
      </button>
      <div className="ml-auto flex flex-wrap justify-end gap-1.5">
        {actions}
        {trends && !trends.length && <Button size="xs" variant="outline" disabled={installing} onClick={() => void addStarters()}><Sparkles />{installing ? "Adding…" : "Add starter behaviors"}</Button>}
        <Button size="xs" variant="outline" className={traceActionClass} onClick={() => setMarking(true)}><Flag />Add release marker</Button>
        <Button size="xs" variant="outline" className={traceActionClass} onClick={() => setCreating(true)}><Plus />New behavior</Button>
      </div>
    </header>
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error} <button className="underline" onClick={onReload}>Retry</button></p>}
    {!collapsed && <>
      {!trends && !error && <p role="status" className="py-2 text-xs text-muted-foreground">Loading behaviors…</p>}
      {trends && !trends.length && <p className="rounded border border-border px-3 py-4 text-xs text-muted-foreground">No behaviors yet. Add the starter set (frustration, tool errors, repeated calls…) or define your own.</p>}
      {sorted.length > 0 && <div className="grid gap-x-4 rounded border border-border px-1 py-1 sm:grid-cols-2 xl:grid-cols-3">
        {sorted.map((t) => {
          const active = t.behavior.id === focusedId;
          return <button key={t.behavior.id} type="button" aria-pressed={active} onClick={() => onFocus(active ? null : t.behavior.id)}
            title={active ? "Show all traces" : `Show traces with ${t.behavior.name}`}
            className={cn("flex h-9 min-w-0 items-center gap-2 rounded px-2 text-left text-xs transition-colors", active ? "bg-brand-500/10 ring-1 ring-brand-500/40" : "hover:bg-surface", !t.behavior.enabled && "text-muted-foreground")}>
            <span className={cn("size-1.5 shrink-0 rounded-full", ACTOR_COLOR[t.behavior.actor].dot, !t.behavior.enabled && "opacity-40")} />
            <span className="min-w-0 flex-1 truncate font-medium"><SeverityDot severity={t.behavior.severity} />{t.behavior.name}{!t.behavior.enabled && <span className="ml-1.5 font-normal text-muted-foreground/70">Off</span>}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground" title="Hits in the last 7 days">{t.last_7_days}</span>
            <Sparkline series={t.series} className={cn("hidden h-5 w-16 shrink-0 sm:block", !t.behavior.enabled && "opacity-40")} />
          </button>;
        })}
      </div>}
      {focused && <FocusedBehavior trend={focused} releases={releases} onClose={() => onFocus(null)} />}
    </>}
    <NewBehaviorDialog open={creating} onOpenChange={setCreating} onCreated={() => onReload()} />
    <ReleaseDialog open={marking} onOpenChange={setMarking} agents={agents} onCreated={() => loadReleases()} />
  </section>;
}

/** The chosen behavior's hits by day with release markers, its definition, and a link to its page. */
function FocusedBehavior({ trend, releases, onClose }: { trend: BehaviorTrend; releases: Release[]; onClose: () => void }) {
  const b = trend.behavior;
  const total = trend.series.reduce((n, d) => n + d.hits, 0);
  return <section aria-label={`${b.name} over time`} className="mt-2 rounded border border-border p-3">
    <header className="mb-2 flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <h3 className="flex items-center gap-2 text-[13px] font-semibold"><span className={cn("size-2 rounded-full", ACTOR_COLOR[b.actor].dot)} />{b.name}</h3>
        {b.definition && <p className="mt-0.5 line-clamp-2 max-w-3xl text-xs text-muted-foreground">{b.definition}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground">
          <SeverityTag severity={b.severity} /><span>{DETECTOR_LABEL[b.detector]}</span>
          <span className="tabular-nums">{total} hit{total === 1 ? "" : "s"} in {trend.series.length} days, {trend.last_7_days} in the last 7</span>
        </p>
      </div>
      <Button asChild size="xs" variant="outline"><Link href={`/reward-models/behaviors/${b.id}`}>Open<ArrowUpRight /></Link></Button>
      <Button size="icon-xs" variant="ghost" aria-label="Show all traces" title="Show all traces" onClick={onClose}><X /></Button>
    </header>
    <HitsChart buckets={dailyBuckets(trend.series)} releases={releases} unit="day" />
  </section>;
}
