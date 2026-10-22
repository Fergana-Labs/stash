"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Check, ChevronDown, ChevronRight, Loader2, Pencil, Search, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { AddToTestSetDialog } from "@/components/test-sets/test-set-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import {
  ActorChip, EnabledSwitch, FieldLabel, HitsChart, ReleaseDialog, SaveToEvalDialog, SeverityTag, dailyBuckets, hourlyBuckets, inputCls, selectCls,
} from "@/components/behaviors/behavior-ui";
import {
  ACTORS, SEVERITIES, compareAroundRelease, deleteBehavior, getBehavior, getBehaviorOverview, getTriage, humanize, listBehaviorHits, listReleases, promoteBehavior,
  reviewHit, searchBehaviorTraces, startTriage, stepWindow, traceStepHref, updateBehavior,
  type Actor, type AlertConfig, type Behavior, type BehaviorHit, type BehaviorInput, type BehaviorTrend, type ChannelKind, type Release, type ReleaseComparison,
  type SearchBehavior, type SearchResult, type Severity, type Triage, type Verdict,
} from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";

type ReviewFilter = "all" | "unreviewed" | "confirmed";
const REVIEW_TABS: { value: ReviewFilter; label: string }[] = [
  { value: "all", label: "All" }, { value: "unreviewed", label: "Unreviewed" }, { value: "confirmed", label: "Confirmed" },
];
const RANGES = [{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }];
const pct = (v: number | null | undefined) => v == null ? "—" : `${Math.round(v * 100)}%`;
const detectorLabel = (b: Behavior) => b.detector === "rule" ? "Built-in" : b.detector === "agent_judge" ? "Described in words, each hit verified by the Agent Judge" : "Described in words";

export default function BehaviorClient({ id }: { id: string }) {
  const router = useRouter();
  const confirm = useConfirm();
  const [behavior, setBehavior] = useState<Behavior | null>(null);
  const [trend, setTrend] = useState<BehaviorTrend | null>(null);
  const [hitTimes, setHitTimes] = useState<number[] | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [confirmedWindows, setConfirmedWindows] = useState<{ trace_id: string; start_idx: number; end_idx: number }[]>([]);
  useBreadcrumbs([{ label: "Traces", href: "/reward-models" }, { label: "Behaviors", href: `/reward-models?behavior=${encodeURIComponent(id)}` }, { label: behavior?.name ?? "Behavior" }], `behavior-${id}-${behavior?.name ?? ""}`);

  const load = useCallback(async () => {
    try {
      setBehavior(await getBehavior(id));
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  const loadReleases = useCallback(() => {
    // Release markers are an overlay; the page works without them.
    listReleases().then((r) => setReleases(r.releases)).catch(() => setReleases([]));
  }, []);
  useEffect(() => { loadReleases(); }, [loadReleases]);

  useEffect(() => {
    let cancelled = false;
    getBehaviorOverview(days).then((o) => { if (!cancelled) setTrend(o.behaviors.find((t) => t.behavior.id === id) ?? null); })
      .catch((e) => { if (!cancelled) toast.error(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [id, days, behavior?.version]);

  // A week or less reads better hour by hour; that needs individual hit times.
  useEffect(() => {
    if (days > 7) { setHitTimes(null); return; }
    let cancelled = false;
    listBehaviorHits(id, { limit: 200 }).then(({ hits }) => {
      if (!cancelled) setHitTimes(hits.filter((h) => h.review !== "rejected").map((h) => new Date(h.trace_created_at ?? h.created_at).getTime()));
    }).catch((e) => { if (!cancelled) toast.error(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [id, days, behavior?.version]);

  async function patch(changes: Partial<BehaviorInput>, success = "Saved") {
    try {
      setBehavior(await updateBehavior(id, changes));
      toast.success(success);
      return true;
    } catch (e) {
      toast.error(errorMessage(e));
      return false;
    }
  }

  async function remove() {
    if (!behavior) return;
    if (!await confirm({ title: `Delete “${behavior.name}”?`, body: "Its hits and alert history are deleted too.", confirmLabel: "Delete" })) return;
    try {
      await deleteBehavior(id);
      router.push("/reward-models");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  async function promote() {
    try {
      const res = await promoteBehavior(id);
      setBehavior(res.behavior);
      toast.success(`Created an eval with ${res.examples} reviewed example${res.examples === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  if (!behavior) {
    return <EvalPageFrame>{error
      ? <p role="alert" className="text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>
      : <p role="status" className="text-xs text-muted-foreground">Loading behavior…</p>}</EvalPageFrame>;
  }

  const series = trend?.series ?? [];
  const scanned = series.reduce((n, d) => n + d.traces_scanned, 0);
  const withHit = series.reduce((n, d) => n + d.traces_with_hit, 0);
  const total = series.reduce((n, d) => n + d.hits, 0);
  const hourly = days <= 7;
  const buckets = hourly ? (hitTimes ? hourlyBuckets(hitTimes, days) : []) : dailyBuckets(series);

  return <EvalPageFrame title={behavior.name} description={behavior.definition || undefined}
    actions={<div className="flex items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><EnabledSwitch checked={behavior.enabled} label="Monitor this behavior" onChange={(enabled) => void patch({ enabled }, enabled ? "Monitoring on" : "Monitoring off")} />{behavior.enabled ? "Monitoring" : "Off"}</span>
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button size="sm" variant="outline">Add to eval<ChevronDown /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60 text-xs">
          {behavior.eval_id
            ? <DropdownMenuItem asChild className="text-xs"><Link href={`/reward-models/evals/${behavior.eval_id}`}>Open this behavior’s eval<ArrowUpRight className="ml-auto" /></Link></DropdownMenuItem>
            : <DropdownMenuItem className="text-xs" onSelect={() => void promote()}>New eval from this behavior</DropdownMenuItem>}
          <DropdownMenuItem className="text-xs" disabled={!confirmedWindows.length} onSelect={() => setAdding(true)}>Add confirmed hits to an eval…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button size="sm" variant="ghost" aria-label="Delete behavior" title="Delete behavior" onClick={() => void remove()}><Trash2 /></Button>
    </div>}>
    <div className="mb-5 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <ActorChip actor={behavior.actor} /><SeverityTag severity={behavior.severity} />
      <span>{detectorLabel(behavior)}</span>
      {behavior.last_alert_at && <span>Last alert {relativeTime(behavior.last_alert_at)}</span>}
    </div>

    <section aria-label="Hits over time" className="mb-6 rounded border border-border p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{total} hit{total === 1 ? "" : "s"} {hourly ? "by hour" : "by day"}</h2>
          {trend && <p className="mt-0.5 text-xs text-muted-foreground">In {pct(scanned ? withHit / scanned : null)} of scanned traces ({withHit} of {scanned}), {trend.last_7_days} hits in the last 7 days</p>}
        </div>
        <Select aria-label="Time range" value={String(days)} onChange={(v) => setDays(Number(v))} options={RANGES} className="h-8 w-36 px-2 text-xs" />
      </header>
      {hourly && !hitTimes ? <p role="status" className="flex h-48 items-center justify-center text-xs text-muted-foreground">Loading hits…</p> : <HitsChart buckets={buckets} releases={releases} unit={hourly ? "hour" : "day"} />}
    </section>

    <HitTable behaviorId={id} days={days} onConfirmed={setConfirmedWindows} />

    <div className="mb-6 grid items-start gap-4 lg:grid-cols-2">
      <CompareCard behaviorId={id} releases={releases} onReleased={loadReleases} />
      <TriageCard behaviorId={id} />
    </div>

    <DefinitionSection behavior={behavior} onSave={patch} />
    <SaveToEvalDialog open={adding} onOpenChange={setAdding} windows={confirmedWindows} />
  </EvalPageFrame>;
}

/** Before/after hit rates around a release marker, and whether the change is more than noise. */
function CompareCard({ behaviorId, releases, onReleased }: { behaviorId: string; releases: Release[]; onReleased: () => void }) {
  const [releaseId, setReleaseId] = useState("");
  const [data, setData] = useState<ReleaseComparison | null>(null);
  const [error, setError] = useState("");
  const [marking, setMarking] = useState(false);
  const sorted = [...releases].sort((a, b) => b.released_at.localeCompare(a.released_at));
  const chosen = releaseId || sorted[0]?.id || "";

  useEffect(() => {
    if (!chosen) { setData(null); return; }
    let cancelled = false;
    setData(null); setError("");
    compareAroundRelease(behaviorId, chosen).then((d) => { if (!cancelled) setData(d); }).catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [behaviorId, chosen]);

  const side = (label: string, w: ReleaseComparison["before"]) => <div className="rounded border border-border px-3 py-2">
    <div className="text-[11px] text-muted-foreground">{label}</div>
    <div className="text-lg font-semibold tabular-nums">{pct(w.rate)}</div>
    <div className="text-[11px] text-muted-foreground">{w.with_hit} of {w.traces} traces{w.ci ? `, 95% CI ${pct(w.ci[0])}–${pct(w.ci[1])}` : ""}</div>
  </div>;

  return <section aria-label="Compare around a release" className="rounded border border-border p-4">
    <header className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-sm font-semibold">Compare around a release</h2>
      {sorted.length > 0 && <Select aria-label="Release" value={chosen} onChange={setReleaseId} options={sorted.map((r) => ({ value: r.id, label: `${r.label}${r.agent ? `, ${r.agent}` : ""}` }))} className="h-7 w-48 px-2 text-xs" />}
    </header>
    {!sorted.length ? <p className="text-xs text-muted-foreground">No releases marked yet. <button type="button" className="underline" onClick={() => setMarking(true)}>Add a release marker</button> to compare this behavior’s rate before and after a change.</p>
      : error ? <p role="alert" className="text-xs text-destructive">{error}</p>
      : !data ? <p role="status" className="text-xs text-muted-foreground">Comparing…</p>
      : <div className="grid gap-2">
        <div className="grid grid-cols-2 gap-2">{side(`${data.window_days} days before`, data.before)}{side(`${data.window_days} days after`, data.after)}</div>
        <p className="m-0 text-xs">{data.change == null ? "Not enough traces to compare."
          : <><b className={data.change > 0 ? "text-destructive" : data.change < 0 ? "text-success" : undefined}>{data.change > 0 ? "+" : ""}{Math.round(data.change * 100)} pts</b> after {data.release.label}, {data.significant ? "a real change (statistically significant)" : <span className="text-muted-foreground">within noise (not significant)</span>}</>}</p>
      </div>}
    <ReleaseDialog open={marking} onOpenChange={setMarking} agents={[]} onCreated={onReleased} />
  </section>;
}

/** Root causes behind this behavior's hits, found by an agent reading the traces. */
function TriageCard({ behaviorId }: { behaviorId: string }) {
  const [triage, setTriage] = useState<Triage | null | undefined>(undefined);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const refresh = useCallback(async () => setTriage((await getTriage(behaviorId)).triage), [behaviorId]);
  useEffect(() => { void refresh().catch(() => setTriage(null)); }, [refresh]);
  const running = triage?.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void refresh().catch((e) => setError(errorMessage(e))); }, 3000);
    return () => clearInterval(timer);
  }, [running, refresh]);

  async function start() {
    setStarting(true); setError("");
    try { await startTriage(behaviorId); await refresh(); } catch (e) { setError(errorMessage(e)); } finally { setStarting(false); }
  }

  const result = triage?.status === "done" ? triage.result : null;
  return <section aria-label="Root causes" className="rounded border border-border p-4">
    <header className="mb-3 flex items-center justify-between gap-2">
      <h2 className="text-sm font-semibold">Root causes</h2>
      <Button size="xs" variant="outline" disabled={starting || running} onClick={() => void start()}>{running ? <><Loader2 className="animate-spin" />Investigating…</> : <><Search />{result ? "Run again" : "Find root causes"}</>}</Button>
    </header>
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
    {triage === undefined ? <p role="status" className="text-xs text-muted-foreground">Loading…</p>
      : running ? <p role="status" className="text-xs text-muted-foreground">Reading the traces with hits and grouping them by cause…</p>
      : triage?.status === "failed" ? <p role="alert" className="text-xs text-destructive">{triage.error || "The investigation failed."}</p>
      : !result ? <p className="text-xs text-muted-foreground">Have an agent read the traces with hits and group them by why they happen.</p>
      : <div className="grid gap-2 text-xs">
        <p className="m-0">{result.summary}</p>
        <ol className="m-0 grid list-none gap-1.5 p-0">{result.root_causes.map((c, i) => <li key={i} className="rounded border border-border px-2.5 py-1.5">
          <div className="flex items-baseline gap-2"><span className="font-medium">{c.title}</span>{c.share != null && <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">{pct(c.share)} of hits</span>}</div>
          <p className="m-0 mt-0.5 text-muted-foreground">{c.explanation}</p>
          {c.traces.length > 0 && <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">{c.traces.slice(0, 4).map((t) => <Link key={`${t.trace_id}-${t.step_idx}`} href={traceStepHref(t.trace_id, t.step_idx ?? 0)} className="max-w-56 truncate text-brand-600 hover:underline">{t.title || "Untitled trace"}{t.step_idx != null && `, step ${t.step_idx + 1}`}</Link>)}</div>}
        </li>)}</ol>
        {result.suggested_fixes.length > 0 && <div><h3 className="m-0 mb-1 text-[12px] font-semibold">Suggested fixes</h3><ul className="m-0 list-disc space-y-0.5 pl-4">{result.suggested_fixes.map((f, i) => <li key={i}>{f}</li>)}</ul></div>}
        <p className="m-0 text-[11px] text-muted-foreground">Investigated {relativeTime(triage!.created_at)}</p>
      </div>}
  </section>;
}

/** The hit's own evidence, which is what a reviewer judges; the trace's last answer only when a hit has none. */
function FlaggedCell({ quote, reason, fallback }: { quote: string | null; reason: string | null; fallback: string }) {
  if (!quote) return <span className="line-clamp-3 text-muted-foreground">{fallback}</span>;
  return <div className="grid gap-0.5">
    <span className="line-clamp-3">“{quote}”</span>
    {reason && <span className="line-clamp-2 text-[11px] text-muted-foreground" title={reason}>{reason}</span>}
  </div>;
}

/** Traces with a hit: filter, open, and confirm or reject each hit. */
function HitTable({ behaviorId, days, onConfirmed }: { behaviorId: string; days: number; onConfirmed: (windows: { trace_id: string; start_idx: number; end_idx: number }[]) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [rows, setRows] = useState<SearchResult[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  // Reviewer reasons by hit ID. Search rows don't carry them, so they come from the hits list.
  const [notes, setNotes] = useState<Record<string, string>>({});
  // What each hit flagged (its quote and the detector's reason), from the same list.
  const [flagged, setFlagged] = useState<Record<string, Pick<BehaviorHit, "evidence" | "note">>>({});
  const [asking, setAsking] = useState<{ hitId: string; verdict: Verdict } | null>(null);
  const [testing, setTesting] = useState<{ trace_id: string; end_idx: number; title?: string } | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    let cancelled = false;
    // Notes are an annotation on the table; it works without them.
    listBehaviorHits(behaviorId, { limit: 200 }).then(({ hits }) => {
      if (cancelled) return;
      setNotes(Object.fromEntries(hits.filter((h) => h.review_note).map((h) => [h.id, h.review_note!])));
      setFlagged(Object.fromEntries(hits.map((h) => [h.id, { evidence: h.evidence, note: h.note }])));
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [behaviorId]);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      searchBehaviorTraces({ q: query, behaviors: [behaviorId], days, limit: 100, rerank: !!query.trim() })
        .then((r) => { if (!cancelled) { setRows(r.results); setError(""); } })
        .catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    }, query.trim() ? 600 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [behaviorId, days, query]);

  const hitOf = (r: SearchResult) => r.behaviors.find((b) => b.behavior_id === behaviorId) ?? null;
  useEffect(() => {
    onConfirmed((rows ?? []).flatMap((r) => r.behaviors.filter((b) => b.behavior_id === behaviorId && b.review === "confirmed").map((b) => ({ trace_id: r.trace_id, start_idx: b.start_idx, end_idx: b.end_idx }))));
  }, [rows, behaviorId, onConfirmed]);

  async function review(hit: SearchBehavior, verdict: Verdict | null) {
    setBusy(hit.id);
    try {
      await reviewHit(hit.id, verdict);
      setRows((cur) => cur?.map((r) => ({ ...r, behaviors: r.behaviors.map((b) => b.id === hit.id ? { ...b, review: verdict } : b) })) ?? cur);
      setNotes((cur) => { const next = { ...cur }; delete next[hit.id]; return next; });
      setDraft("");
      setAsking(verdict ? { hitId: hit.id, verdict } : null);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  /** The optional reason after a verdict; the detector reads it as an example of where the line is. */
  async function saveNote() {
    const note = draft.trim();
    if (!asking || !note) { setAsking(null); return; }
    setBusy(asking.hitId);
    try {
      await reviewHit(asking.hitId, asking.verdict, note);
      setNotes((cur) => ({ ...cur, [asking.hitId]: note }));
      setAsking(null);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  const shown = (rows ?? []).filter((r) => {
    const hit = hitOf(r);
    return filter === "all" || (filter === "unreviewed" ? !hit?.review : hit?.review === filter);
  });
  return <section aria-label="Traces with a hit" className="mb-6">
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <label className="flex h-8 w-80 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Filter hits" placeholder="Filter traces with a hit…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label>
      <nav aria-label="Review status" className="flex gap-1 text-xs">{REVIEW_TABS.map((t) => <button key={t.value} type="button" aria-pressed={filter === t.value} onClick={() => setFilter(t.value)}
        className={cn("rounded-md px-2 py-1", filter === t.value ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>{t.label}</button>)}</nav>
      <span className="ml-auto text-xs text-muted-foreground">{rows ? `${shown.length} traces` : ""}</span>
    </div>
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Hits" className="w-full min-w-[860px] table-fixed text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th className="w-32">Timestamp</th><th className="w-28">Agent</th><th>Input</th><th>What it flagged</th><th className="w-80 text-right">Review</th></tr></thead>
      <tbody>
        {shown.map((r) => {
          const hit = hitOf(r);
          return <tr key={r.trace_id} className="border-b border-border align-top hover:bg-surface/60 [&>td]:px-3 [&>td]:py-2">
            <td className="tabular-nums text-muted-foreground"><Link href={traceStepHref(r.trace_id, hit?.start_idx ?? 0)} className="hover:text-foreground hover:underline">{new Date(r.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Link>
              {hit && <div className="text-[10.5px]">{stepWindow(hit.start_idx, hit.end_idx)}</div>}</td>
            <td className="truncate">{r.agent ?? "—"}</td>
            <td><Link href={traceStepHref(r.trace_id, hit?.start_idx ?? 0)} className="line-clamp-2 hover:underline" title={r.title ?? undefined}>{r.input || r.title || "—"}</Link></td>
            <td><FlaggedCell quote={(hit && flagged[hit.id]?.evidence?.[0]?.quote) || null} reason={(hit && flagged[hit.id]?.note) || null} fallback={r.final_output || r.output || "—"} /></td>
            <td className="text-right">{hit && <div className="inline-flex items-center justify-end gap-1 whitespace-nowrap">
              {hit.review && <span className={cn("mr-1 self-center text-[11px]", hit.review === "confirmed" ? "text-success" : "text-muted-foreground")}>{humanize(hit.review)}</span>}
              {hit.review !== "confirmed" && <Button size="xs" variant="outline" disabled={busy === hit.id} onClick={() => void review(hit, "confirmed")}><Check />Confirm</Button>}
              {hit.review !== "rejected" && <Button size="xs" variant="outline" disabled={busy === hit.id} onClick={() => void review(hit, "rejected")}><X />Reject</Button>}
              {hit.review && <Button size="xs" variant="ghost" disabled={busy === hit.id} onClick={() => void review(hit, null)}>Undo</Button>}
              <Button size="xs" variant="ghost" title="Make this conversation a regression test" onClick={() => setTesting({ trace_id: r.trace_id, end_idx: hit.end_idx, title: r.title ?? undefined })}>Add to test set</Button>
            </div>}
            {hit && asking?.hitId === hit.id && <form className="mt-1.5 flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); void saveNote(); }}>
              <input autoFocus aria-label="Why? (teaches the detector)" placeholder="Why? (teaches the detector)" value={draft} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setAsking(null); }} className="h-6 min-w-0 flex-1 rounded border border-border bg-transparent px-1.5 text-[11px] outline-none focus-visible:border-ring" />
              <Button type="submit" size="xs" disabled={busy === hit.id || !draft.trim()}>Save</Button>
              <Button type="button" size="xs" variant="ghost" onClick={() => setAsking(null)}>Skip</Button>
            </form>}
            {hit?.review && notes[hit.id] && asking?.hitId !== hit.id && <p className="mt-1 text-left text-[11px] text-muted-foreground" title="Reviewer’s reason">“{notes[hit.id]}”</p>}</td>
          </tr>;
        })}
        {!rows && !error && <tr><td colSpan={5} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading hits…</span></td></tr>}
        {rows && !shown.length && <tr><td colSpan={5} className="px-3 py-8 text-muted-foreground">{query.trim() ? "No traces match." : filter === "unreviewed" ? "Nothing to review." : filter === "confirmed" ? "No confirmed hits." : "No hits in this time range."}</td></tr>}
      </tbody>
    </table></div>
    {testing && <AddToTestSetDialog open onOpenChange={(o) => { if (!o) setTesting(null); }} traceId={testing.trace_id} uptoIdx={testing.end_idx} title={testing.title} />}
  </section>;
}

/** Definition and alert: a read view, and one form (one Save) behind Edit. Collapsed by default. */
function DefinitionSection({ behavior, onSave }: { behavior: Behavior; onSave: (changes: Partial<BehaviorInput>, success?: string) => Promise<boolean> }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const alert = behavior.alert;
  return <section aria-label="Definition and alert" className="rounded border border-border">
    <div className="flex items-center justify-between gap-2 px-4 py-3">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex items-center gap-1.5 text-sm font-semibold">{open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}Definition &amp; alert</button>
      {open && !editing && <Button size="xs" variant="outline" onClick={() => setEditing(true)}><Pencil />Edit</Button>}
    </div>
    {open && <div className="border-t border-border px-4 py-3">
      {editing ? <EditForm behavior={behavior} onSave={onSave} onCancel={() => setEditing(false)} />
        : <dl className="m-0 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-[9rem_1fr]">
          <dt className="text-muted-foreground">Who does it</dt><dd className="m-0">{ACTORS.find((a) => a.value === behavior.actor)?.label}</dd>
          <dt className="text-muted-foreground">Detection</dt><dd className="m-0">{detectorLabel(behavior)}</dd>
          <dt className="text-muted-foreground">Definition</dt><dd className="m-0 whitespace-pre-wrap">{behavior.definition || <span className="text-muted-foreground">—</span>}</dd>
          {behavior.examples.length > 0 && <><dt className="text-muted-foreground">Examples</dt><dd className="m-0"><ul className="m-0 list-none space-y-0.5 p-0">{behavior.examples.map((ex, i) => <li key={i}>“{ex}”</li>)}</ul></dd></>}
          <dt className="text-muted-foreground">Severity</dt><dd className="m-0">{humanize(behavior.severity)}</dd>
          <dt className="text-muted-foreground">Alert</dt><dd className="m-0">{alert ? `${alert.threshold}+ hits within ${alert.window_hours}h, at most once every ${alert.cooldown_hours}h, via ${alert.channels.map(humanize).join(" and ")}` : <span className="text-muted-foreground">None</span>}</dd>
          <dt className="text-muted-foreground">Version</dt><dd className="m-0">v{behavior.version}</dd>
        </dl>}
    </div>}
  </section>;
}

function EditForm({ behavior, onSave, onCancel }: { behavior: Behavior; onSave: (changes: Partial<BehaviorInput>, success?: string) => Promise<boolean>; onCancel: () => void }) {
  const builtIn = behavior.detector === "rule";
  const [name, setName] = useState(behavior.name);
  const [actor, setActor] = useState<Actor>(behavior.actor);
  const [verify, setVerify] = useState(behavior.detector === "agent_judge");
  const [definition, setDefinition] = useState(behavior.definition);
  const [examples, setExamples] = useState(behavior.examples.join("\n"));
  const [severity, setSeverity] = useState<Severity>(behavior.severity);
  const [alertOn, setAlertOn] = useState(behavior.alert !== null);
  const [threshold, setThreshold] = useState(String(behavior.alert?.threshold ?? 5));
  const [windowHours, setWindowHours] = useState(String(behavior.alert?.window_hours ?? 24));
  const [cooldown, setCooldown] = useState(String(behavior.alert?.cooldown_hours ?? 24));
  const [channels, setChannels] = useState<ChannelKind[]>(behavior.alert?.channels ?? ["slack", "email"]);
  const [saving, setSaving] = useState(false);
  const confirm = useConfirm();

  const exampleList = examples.split("\n").map((s) => s.trim()).filter(Boolean);
  const detector = builtIn ? "rule" : verify ? "agent_judge" : "llm";
  const alert: AlertConfig | null = alertOn ? { threshold: Number(threshold), window_hours: Number(windowHours), cooldown_hours: Number(cooldown), channels } : null;
  const changes: Partial<BehaviorInput> = {
    ...(name.trim() !== behavior.name && { name: name.trim() }),
    ...(actor !== behavior.actor && { actor }),
    ...(severity !== behavior.severity && { severity }),
    ...(detector !== behavior.detector && { detector }),
    ...(definition.trim() !== behavior.definition && { definition: definition.trim() }),
    ...(JSON.stringify(exampleList) !== JSON.stringify(behavior.examples) && { examples: exampleList }),
    ...(JSON.stringify(alert) !== JSON.stringify(behavior.alert) && { alert }),
  };
  const dirty = Object.keys(changes).length > 0;
  const changesMeaning = !builtIn && ["definition", "examples", "detector"].some((k) => k in changes);
  const alertValid = !alertOn || (Number(threshold) >= 1 && Number(windowHours) >= 1 && Number(windowHours) <= 720 && Number(cooldown) >= 1 && Number(cooldown) <= 720 && channels.length > 0);

  async function save() {
    if (changesMeaning && !await confirm({
      title: "Rescan with the new definition?",
      body: "Changing what this behavior means rescans your traces. Hits nobody reviewed yet are dropped and found again; confirmed and rejected hits are kept.",
      confirmLabel: "Save and rescan", destructive: false,
    })) return;
    setSaving(true);
    if (await onSave(changes, changesMeaning ? "Saved; rescanning traces" : "Saved")) onCancel();
    setSaving(false);
  }

  return <div className="grid gap-4">
    <div className="grid gap-3">
      <FieldLabel label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></FieldLabel>
      <div className="grid grid-cols-2 gap-3">
        <FieldLabel label="Who does it"><Select className={selectCls} aria-label="Actor" value={actor} onChange={(v) => setActor(v as Actor)} options={ACTORS} /></FieldLabel>
        <FieldLabel label="Severity"><Select className={selectCls} aria-label="Severity" value={severity} onChange={(v) => setSeverity(v as Severity)} options={SEVERITIES.map((s) => ({ value: s, label: humanize(s) }))} /></FieldLabel>
      </div>
      <FieldLabel label={builtIn ? "Note" : "Describe it in words"} hint={builtIn ? "Built-in: a rule decides what counts; this note is for people." : undefined}><Textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={4} className="text-xs md:text-xs" /></FieldLabel>
      {!builtIn && <FieldLabel label="Example quotes" hint="One per line."><Textarea value={examples} onChange={(e) => setExamples(e.target.value)} rows={3} className="text-xs md:text-xs" /></FieldLabel>}
      {!builtIn && <label className="flex items-start gap-2 text-xs"><input type="checkbox" className="mt-0.5" checked={verify} onChange={(e) => setVerify(e.target.checked)} />Verify each hit with the Agent Judge (slower, for high-stakes behaviors)</label>}
    </div>
    <fieldset className="grid gap-3 rounded border border-border p-3">
      <legend className="px-1 text-xs font-medium">Alert</legend>
      <label className="flex items-center gap-2 text-xs"><EnabledSwitch checked={alertOn} label="Alert on this behavior" onChange={setAlertOn} />{alertOn ? "Notify when hits spike" : "No alert"}</label>
      {alertOn && <>
        <div className="grid grid-cols-3 gap-3">
          <FieldLabel label="Threshold" hint="hits"><input type="number" min={1} className={inputCls} value={threshold} onChange={(e) => setThreshold(e.target.value)} /></FieldLabel>
          <FieldLabel label="Window" hint="hours"><input type="number" min={1} max={720} className={inputCls} value={windowHours} onChange={(e) => setWindowHours(e.target.value)} /></FieldLabel>
          <FieldLabel label="Cooldown" hint="hours"><input type="number" min={1} max={720} className={inputCls} value={cooldown} onChange={(e) => setCooldown(e.target.value)} /></FieldLabel>
        </div>
        <div className="flex gap-4 text-xs"><span className="font-medium">Channels</span>
          {(["slack", "email"] as ChannelKind[]).map((c) => <label key={c} className="inline-flex items-center gap-1.5"><input type="checkbox" checked={channels.includes(c)} onChange={(e) => setChannels((cur) => e.target.checked ? [...cur, c] : cur.filter((x) => x !== c))} />{humanize(c)}</label>)}
        </div>
        <p className="m-0 text-[11px] text-muted-foreground">Notify when this behavior happens {threshold || "N"}+ times within {windowHours || "N"}h, at most once every {cooldown || "N"}h.</p>
      </>}
    </fieldset>
    {changesMeaning && <p className="m-0 text-[11px] text-amber-700 dark:text-amber-400">Saving changes the behavior’s meaning: traces are rescanned and unreviewed hits are dropped.</p>}
    <div className="flex gap-2"><Button size="sm" disabled={!dirty || saving || !name.trim() || !alertValid} onClick={() => void save()}>{saving ? "Saving…" : "Save"}</Button><Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button></div>
  </div>;
}
