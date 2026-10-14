"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  ACTOR_COLOR, ACTORS, SEVERITIES, createBehavior, createFromTemplate, createRelease, humanize, listBehaviorTemplates, saveWindowsToEval, stepWindow, traceStepHref,
  type Actor, type Behavior, type BehaviorTemplate, type DayPoint, type Release, type SearchBehavior, type SearchResult, type Severity,
} from "@/lib/behaviors-api";
import { imGet, imList, type ModelSummary } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";

export function ActorChip({ actor }: { actor: Actor }) {
  return <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[10.5px] font-medium", ACTOR_COLOR[actor].chip)}>{ACTORS.find((a) => a.value === actor)?.label ?? actor}</span>;
}

/** A small red dot before high-severity names; nothing otherwise. */
export function SeverityDot({ severity }: { severity: Severity }) {
  if (severity !== "high") return null;
  return <span role="img" aria-label="High severity" title="High severity" className="mr-1.5 inline-block size-1.5 shrink-0 rounded-full bg-destructive align-middle" />;
}

export function SeverityTag({ severity }: { severity: Severity }) {
  return <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
    <span className={cn("size-1.5 rounded-full", severity === "high" ? "bg-destructive" : severity === "medium" ? "bg-amber-500" : "bg-muted-foreground/50")} />{humanize(severity)} severity
  </span>;
}

export function BehaviorChip({ name, actor, count, onClick, title }: { name: string; actor: Actor; count?: number; onClick?: () => void; title?: string }) {
  const body = <><span className={cn("size-1.5 shrink-0 rounded-full", ACTOR_COLOR[actor].dot)} /><span className="truncate">{name}</span>{count !== undefined && count > 1 && <span className="shrink-0 tabular-nums text-muted-foreground">×{count}</span>}</>;
  const cls = "inline-flex max-w-48 items-center gap-1 rounded border border-border bg-background px-1.5 py-0.5 text-[11px]";
  return onClick
    ? <button type="button" title={title} onClick={onClick} className={cn(cls, "hover:border-foreground/30")}>{body}</button>
    : <span title={title} className={cls}>{body}</span>;
}

/** One chip per behavior (×count), at most `max`, then "+N". Each links to the behavior's first window. */
export function BehaviorChips({ traceId, behaviors, max = 3 }: { traceId: string; behaviors: SearchBehavior[]; max?: number }) {
  const byBehavior = new Map<string, { first: SearchBehavior; windows: SearchBehavior[] }>();
  for (const b of [...behaviors].sort((x, y) => x.start_idx - y.start_idx)) {
    const entry = byBehavior.get(b.behavior_id);
    if (entry) entry.windows.push(b); else byBehavior.set(b.behavior_id, { first: b, windows: [b] });
  }
  const all = [...byBehavior.values()];
  const shown = all.slice(0, max);
  const rest = all.slice(max);
  return <div className="flex flex-wrap gap-1">
    {shown.map(({ first, windows }) => <Link key={first.behavior_id} href={traceStepHref(traceId, first.start_idx)} title={windows.map((w) => stepWindow(w.start_idx, w.end_idx)).join(", ")}>
      <BehaviorChip name={first.name} actor={first.actor} count={windows.length} />
    </Link>)}
    {rest.length > 0 && <span title={rest.map((r) => r.first.name).join(", ")} className="inline-flex items-center rounded border border-dashed border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">+{rest.length}</span>}
  </div>;
}

/** A switch (track and knob) so it reads as clickable. */
export function EnabledSwitch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onChange(!checked); }}
    className={cn("relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors disabled:opacity-50", checked ? "bg-brand-500" : "bg-muted-foreground/30")}>
    <span className={cn("inline-block size-3 rounded-full bg-white shadow transition-transform", checked ? "translate-x-3.5" : "translate-x-0.5")} />
  </button>;
}

export function Sparkline({ series, className }: { series: DayPoint[]; className?: string }) {
  const max = Math.max(1, ...series.map((d) => d.hits));
  const w = 96, h = 24, step = series.length > 1 ? w / (series.length - 1) : w;
  const points = series.map((d, i) => `${(i * step).toFixed(1)},${(h - 2 - (d.hits / max) * (h - 4)).toFixed(1)}`).join(" ");
  return <svg viewBox={`0 0 ${w} ${h}`} className={cn("h-6 w-24 text-brand-500", className)} role="img" aria-label={`Daily hits, peak ${max}`}>
    {series.length > 0 && <polyline points={points} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />}
  </svg>;
}

export const shortDate = (s: string | Date) => new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export interface HitBucket { start: number; end: number; hits: number; detail?: string }
const HOUR = 3600_000, DAY = 24 * HOUR;

/** Hourly buckets over the last `days` days from individual hit times. */
export function hourlyBuckets(times: number[], days: number, now = Date.now()): HitBucket[] {
  const end = Math.ceil(now / HOUR) * HOUR;
  const start = end - days * DAY;
  const buckets: HitBucket[] = Array.from({ length: days * 24 }, (_, i) => ({ start: start + i * HOUR, end: start + (i + 1) * HOUR, hits: 0 }));
  for (const t of times) {
    const i = Math.floor((t - start) / HOUR);
    if (i >= 0 && i < buckets.length) buckets[i].hits += 1;
  }
  return buckets;
}

/** Daily buckets from the monitoring series (calendar days, local). */
export function dailyBuckets(series: DayPoint[]): HitBucket[] {
  return series.map((d) => {
    const start = new Date(`${d.day.slice(0, 10)}T00:00:00`).getTime();
    return { start, end: start + DAY, hits: d.hits, detail: `${d.traces_with_hit} of ${d.traces_scanned} scanned traces` };
  });
}

/** Integer ticks only, so low counts never repeat a label (0, 1, 1, 2…). */
export function integerTicks(max: number): number[] {
  if (max <= 4) return Array.from({ length: Math.max(1, max) + 1 }, (_, i) => i);
  const step = Math.ceil(max / 4);
  const ticks: number[] = [];
  for (let t = 0; t < max + step; t += step) ticks.push(t);
  return ticks;
}

/** Hits over time as bars, with release markers as dashed vertical lines. */
export function HitsChart({ buckets, releases = [], unit }: { buckets: HitBucket[]; releases?: Release[]; unit: "hour" | "day" }) {
  if (!buckets.length) return <p className="flex h-40 items-center justify-center text-xs text-muted-foreground">No data yet.</p>;
  const ticks = integerTicks(Math.max(0, ...buckets.map((b) => b.hits)));
  const top = ticks.at(-1)!;
  const left = 36, right = 1184, t = 18, bottom = 160;
  const from = buckets[0].start, to = buckets.at(-1)!.end;
  const x = (ms: number) => left + ((ms - from) / (to - from)) * (right - left);
  const y = (n: number) => bottom - (n / Math.max(1, top)) * (bottom - t);
  const bw = (right - left) / buckets.length;
  const fmt = (ms: number) => unit === "hour"
    ? new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" })
    : shortDate(new Date(ms));
  const marks = releases.filter((r) => { const ms = new Date(r.released_at).getTime(); return ms >= from && ms <= to; });
  return <figure className="m-0" aria-label="Hits over time">
    <svg viewBox="0 0 1200 186" className="h-auto w-full" role="img" aria-label={`Hits per ${unit}`}>
      {ticks.map((tick) => <g key={tick}><line x1={left} x2={right} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.08} /><text x={left - 6} y={y(tick) + 4} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{tick}</text></g>)}
      {buckets.map((b) => <g key={b.start}>
        {b.hits > 0 && <rect x={x(b.start) + bw * 0.12} width={Math.max(1, bw * 0.76)} y={y(b.hits)} height={bottom - y(b.hits)} rx={Math.min(2, bw / 4)} className="fill-brand-500/75" />}
        <rect x={x(b.start)} width={bw} y={t} height={bottom - t} fill="transparent"><title>{fmt(b.start)} · {b.hits} hit{b.hits === 1 ? "" : "s"}{b.detail ? ` in ${b.detail}` : ""}</title></rect>
      </g>)}
      {marks.map((r) => { const mx = x(new Date(r.released_at).getTime()); return <g key={r.id} data-release-marker>
        <line x1={mx} x2={mx} y1={t - 6} y2={bottom} stroke="currentColor" strokeDasharray="3 3" opacity={0.6} />
        <text x={mx > right - 160 ? mx - 3 : mx + 3} y={t - 8} fontSize={10} textAnchor={mx > right - 160 ? "end" : "start"} fill="currentColor" opacity={0.8}>{r.label}</text>
        <title>{r.label}{r.agent ? ` · ${r.agent}` : ""} · {new Date(r.released_at).toLocaleString()}{r.note ? `\n${r.note}` : ""}</title>
      </g>; })}
      <text x={left} y={178} fontSize={10} fill="currentColor" opacity={0.55}>{fmt(from)}</text>
      <text x={right} y={178} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{fmt(buckets.at(-1)!.start)}</text>
    </svg>
  </figure>;
}

export function ChangeLabel({ change, current }: { change: number | null; current: number }) {
  if (change === null) return <span className="text-muted-foreground">{current ? "new" : "—"}</span>;
  const pct = Math.round(change * 100);
  return <span className={cn("tabular-nums", pct > 0 ? "text-destructive" : pct < 0 ? "text-success" : "text-muted-foreground")}>{pct > 0 ? "+" : ""}{pct}%</span>;
}

/** The outcome of a trace as a small humanized tag. */
export function OutcomeTag({ outcome }: { outcome: string | null | undefined }) {
  if (!outcome) return null;
  const bad = outcome === "error" || outcome === "not_found";
  return <span className={cn("inline-flex rounded border px-1 py-px text-[10px]", bad ? "border-destructive/30 text-destructive" : outcome === "answer" ? "border-emerald-500/30 text-emerald-700 dark:text-emerald-400" : "border-border text-muted-foreground")}>{humanize(outcome)}</span>;
}

/** Strip transcript render prefixes ("steps 2–5:", "[1] USER") from a search snippet. */
export function cleanSnippet(text: string): string {
  return text
    .replace(/^\s*steps?\s+\d+(?:\s*[–-]\s*\d+)?\s*:\s*/i, "")
    .replace(/\[\d+\]\s*(?:USER|ASSISTANT|AGENT|TOOL|SYSTEM|ENVIRONMENT)(?:\s*\([^)]*\))?\s*:?\s*/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** A clean quote with the query terms in bold. */
export function QuoteSnippet({ text, query }: { text: string; query: string }) {
  const terms = [...new Set(query.toLowerCase().split(/\s+/).filter((w) => w.length > 2))].map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!terms.length) return <>“{text}”</>;
  const parts = text.split(new RegExp(`(${terms.join("|")})`, "gi"));
  return <>“{parts.map((p, i) => i % 2 ? <b key={i} className="font-semibold text-foreground">{p}</b> : <Fragment key={i}>{p}</Fragment>)}”</>;
}

/** Results in order, with traces from one session pulled together under that session. */
export function groupBySession(results: SearchResult[]): { session: string | null; rows: SearchResult[] }[] {
  const counts = new Map<string, number>();
  for (const r of results) if (r.session_id) counts.set(r.session_id, (counts.get(r.session_id) ?? 0) + 1);
  const groups: { session: string | null; rows: SearchResult[] }[] = [];
  const bySession = new Map<string, { session: string | null; rows: SearchResult[] }>();
  for (const r of results) {
    if (r.session_id && (counts.get(r.session_id) ?? 0) > 1) {
      const existing = bySession.get(r.session_id);
      if (existing) { existing.rows.push(r); continue; }
      const group = { session: r.session_id, rows: [r] };
      bySession.set(r.session_id, group);
      groups.push(group);
    } else groups.push({ session: null, rows: [r] });
  }
  return groups;
}

const inputCls = "h-8 w-full rounded-md border border-border bg-transparent px-2 text-xs outline-none focus-visible:border-ring";

export function FieldLabel({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="grid gap-1 text-xs"><span className="font-medium">{label}</span>{children}{hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}</label>;
}

export { inputCls };

/** Behaviors as one multi-select dropdown. */
export function BehaviorMultiSelect({ behaviors, selected, onChange }: { behaviors: Pick<Behavior, "id" | "name" | "actor">[]; selected: Set<string>; onChange: (next: Set<string>) => void }) {
  const names = behaviors.filter((b) => selected.has(b.id)).map((b) => b.name);
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label="Behavior filter" className={cn("inline-flex h-8 max-w-64 items-center gap-1.5 rounded-md border border-border px-2 text-xs", selected.size ? "text-foreground" : "text-muted-foreground")}>
        <span className="truncate">{!selected.size ? "Behavior: any" : names.length === 1 ? names[0] : `${names.length} behaviors`}</span><ChevronDown className="size-3 shrink-0" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="max-h-80 w-64 overflow-y-auto">
      {behaviors.map((b) => <DropdownMenuCheckboxItem key={b.id} checked={selected.has(b.id)} onSelect={(e) => e.preventDefault()}
        onCheckedChange={(on) => { const next = new Set(selected); if (on) next.add(b.id); else next.delete(b.id); onChange(next); }} className="text-xs">
        <span className={cn("size-1.5 shrink-0 rounded-full", ACTOR_COLOR[b.actor].dot)} />{b.name}
      </DropdownMenuCheckboxItem>)}
      {selected.size > 0 && <><DropdownMenuSeparator /><DropdownMenuItem className="text-xs" onSelect={() => onChange(new Set())}>Clear</DropdownMenuItem></>}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** Create a behavior from a template, or describe a custom one in words. */
export function NewBehaviorDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (b: Behavior) => void }) {
  const [templates, setTemplates] = useState<BehaviorTemplate[] | null>(null);
  const [name, setName] = useState("");
  const [actor, setActor] = useState<Actor>("agent");
  const [verify, setVerify] = useState(false);
  const [definition, setDefinition] = useState("");
  const [examples, setExamples] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [saving, setSaving] = useState<string | null>(null);
  const valid = name.trim() && definition.trim();

  useEffect(() => {
    if (!open || templates) return;
    // Templates are a shortcut; without them the custom form still works.
    listBehaviorTemplates().then((r) => setTemplates(r.templates)).catch(() => setTemplates([]));
  }, [open, templates]);

  function done(created: Behavior) {
    onCreated(created);
    onOpenChange(false);
    setName(""); setDefinition(""); setExamples(""); setVerify(false);
  }

  async function fromTemplate(t: BehaviorTemplate) {
    setSaving(t.slug);
    try { done(await createFromTemplate(t.slug)); } catch (e) { toast.error(errorMessage(e)); } finally { setSaving(null); }
  }

  async function submit() {
    setSaving("custom");
    try {
      done(await createBehavior({
        name: name.trim(), actor, detector: verify ? "agent_judge" : "llm", definition: definition.trim(),
        examples: examples.split("\n").map((s) => s.trim()).filter(Boolean),
        rule: null, severity, enabled: true, alert: null,
      }));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(null);
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
    <DialogHeader><DialogTitle>New behavior</DialogTitle><DialogDescription>A named pattern Stash tags on trace windows as traces come in.</DialogDescription></DialogHeader>
    {!!templates?.length && <section aria-label="Templates" className="grid min-w-0 gap-1.5">
      <h3 className="m-0 text-xs font-medium">Start from a template</h3>
      <ul className="m-0 grid max-h-56 list-none grid-cols-1 gap-1 overflow-x-hidden overflow-y-auto p-0">{templates.map((t) => <li key={t.slug} className="min-w-0">
        <button type="button" disabled={!!saving} onClick={() => void fromTemplate(t)} className="flex w-full items-start gap-2 rounded border border-border px-2.5 py-1.5 text-left text-xs hover:border-foreground/30 disabled:opacity-60">
          <span className={cn("mt-1 size-1.5 shrink-0 rounded-full", ACTOR_COLOR[t.actor].dot)} />
          <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.name}{t.verify && <span className="ml-1.5 text-[10.5px] font-normal text-muted-foreground">· verified by the Agent Judge</span>}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{t.definition}</span></span>
          {saving === t.slug && <span className="text-[11px] text-muted-foreground">Adding…</span>}
        </button>
      </li>)}</ul>
      <h3 className="m-0 mt-2 text-xs font-medium">Or describe your own</h3>
    </section>}
    <div className="grid gap-3">
      <FieldLabel label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Refund promised without checking policy" /></FieldLabel>
      <div className="grid grid-cols-2 gap-3">
        <FieldLabel label="Who does it"><Select aria-label="Actor" value={actor} onChange={(v) => setActor(v as Actor)} options={ACTORS} /></FieldLabel>
        <FieldLabel label="Severity"><Select aria-label="Severity" value={severity} onChange={(v) => setSeverity(v as Severity)} options={SEVERITIES.map((s) => ({ value: s, label: humanize(s) }))} /></FieldLabel>
      </div>
      <FieldLabel label="Describe it in words" hint="What counts, in plain language. A model reads this to tag trace windows.">
        <Textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={3} className="text-xs md:text-xs" />
      </FieldLabel>
      <FieldLabel label="Example quotes" hint="Optional. One per line: short excerpts that show the behavior.">
        <Textarea value={examples} onChange={(e) => setExamples(e.target.value)} rows={2} className="text-xs md:text-xs" />
      </FieldLabel>
      <label className="flex items-start gap-2 text-xs"><input type="checkbox" className="mt-0.5" checked={verify} onChange={(e) => setVerify(e.target.checked)} />Verify each hit with the Agent Judge (slower, for high-stakes behaviors)</label>
    </div>
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={!valid || !!saving} onClick={() => void submit()}>{saving === "custom" ? "Creating…" : "Create behavior"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}

/** Mark a release so trend charts show it and rates can be compared around it. */
export function ReleaseDialog({ open, onOpenChange, agents, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; agents: string[]; onCreated: (r: Release) => void }) {
  const local = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
  const [label, setLabel] = useState("");
  const [agent, setAgent] = useState("");
  const [at, setAt] = useState(local);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) setAt(local()); }, [open]);

  async function save() {
    setSaving(true);
    try {
      const release = await createRelease({ label: label.trim(), agent: agent || null, released_at: new Date(at).toISOString(), ...(note.trim() && { note: note.trim() }) });
      toast.success("Release marked");
      onCreated(release);
      onOpenChange(false);
      setLabel(""); setNote("");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-md">
    <DialogHeader><DialogTitle>Add release marker</DialogTitle><DialogDescription>Shows on behavior charts so you can compare rates before and after a change.</DialogDescription></DialogHeader>
    <div className="grid gap-3">
      <FieldLabel label="Label"><input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="v2.3 prompt update" /></FieldLabel>
      <div className="grid grid-cols-2 gap-3">
        <FieldLabel label="Agent" hint="Optional">{agents.length
          ? <Select aria-label="Agent" value={agent} onChange={setAgent} options={[{ value: "", label: "All agents" }, ...agents.map((a) => ({ value: a, label: a }))]} />
          : <input className={inputCls} value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="All agents" />}</FieldLabel>
        <FieldLabel label="When"><input type="datetime-local" className={inputCls} value={at} onChange={(e) => setAt(e.target.value)} /></FieldLabel>
      </div>
      <FieldLabel label="Note" hint="Optional"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></FieldLabel>
    </div>
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={!label.trim() || !at || saving} onClick={() => void save()}>{saving ? "Saving…" : "Add marker"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}

export interface TraceWindow { trace_id: string; start_idx: number; end_idx: number }

/** Add trace windows to an existing eval as labeled examples. */
export function SaveToEvalDialog({ open, onOpenChange, windows, onSaved }: { open: boolean; onOpenChange: (open: boolean) => void; windows: TraceWindow[]; onSaved?: () => void }) {
  const [evals, setEvals] = useState<ModelSummary[] | null>(null);
  const [evalId, setEvalId] = useState("");
  const [labels, setLabels] = useState<string[]>([]);
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || evals) return;
    imList().then((r) => { setEvals(r.models); setEvalId((cur) => cur || r.models.find((m) => m.output_type === "choice")?.id || ""); })
      .catch((e) => setError(errorMessage(e)));
  }, [open, evals]);

  useEffect(() => {
    if (!evalId) { setLabels([]); return; }
    let cancelled = false;
    imGet(evalId).then((d) => {
      if (cancelled) return;
      const ids = (d.draft ?? d.active)?.labels.map((l) => l.id) ?? [];
      setLabels(ids);
      setLabel(ids[0] ?? "");
    }).catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [evalId]);

  async function save() {
    setSaving(true);
    try {
      const res = await saveWindowsToEval({ eval_id: evalId, label, windows });
      toast.success(`Added ${res.examples.length} example${res.examples.length === 1 ? "" : "s"} to the eval`);
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const choices = evals?.filter((m) => m.output_type === "choice") ?? [];
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-md">
    <DialogHeader><DialogTitle>Add to eval</DialogTitle><DialogDescription>{windows.length} trace window{windows.length === 1 ? "" : "s"} become labeled examples.</DialogDescription></DialogHeader>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {!evals && !error ? <p role="status" className="text-xs text-muted-foreground">Loading evals…</p>
      : !choices.length ? <p className="text-xs text-muted-foreground">No label evals yet. Create one under Evals first.</p>
      : <div className="grid gap-3">
        <FieldLabel label="Eval"><Select aria-label="Eval" value={evalId} onChange={setEvalId} options={choices.map((m) => ({ value: m.id, label: m.name }))} /></FieldLabel>
        <FieldLabel label="Label">{labels.length
          ? <Select aria-label="Label" value={label} onChange={setLabel} options={labels.map((l) => ({ value: l, label: humanize(l) }))} />
          : <input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" />}</FieldLabel>
      </div>}
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={!evalId || !label || saving || !windows.length} onClick={() => void save()}>{saving ? "Adding…" : "Add to eval"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}
