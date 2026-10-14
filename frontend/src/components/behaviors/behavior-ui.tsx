"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/components/reward-models/rm-text";
import {
  ACTORS, SEVERITIES, createBehavior, saveWindowsToEval,
  type Actor, type Behavior, type DayPoint, type Detector, type Severity,
} from "@/lib/behaviors-api";
import { imGet, imList, type ModelSummary } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";

const ACTOR_STYLE: Record<Actor, string> = {
  user: "bg-blue-500/10 text-blue-700 dark:text-blue-300",
  agent: "bg-brand-500/12 text-brand-600",
  environment: "bg-teal-500/10 text-teal-700 dark:text-teal-300",
};

export function ActorChip({ actor }: { actor: Actor }) {
  return <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[10.5px] font-medium", ACTOR_STYLE[actor])}>{ACTORS.find((a) => a.value === actor)?.label ?? actor}</span>;
}

export function SeverityTag({ severity }: { severity: Severity }) {
  return <span className={cn("inline-flex items-center gap-1 text-[11px] capitalize text-muted-foreground")}>
    <span className={cn("size-1.5 rounded-full", severity === "high" ? "bg-destructive" : severity === "medium" ? "bg-amber-500" : "bg-muted-foreground/50")} />{severity}
  </span>;
}

export function BehaviorChip({ name, actor, onClick, title }: { name: string; actor: Actor; onClick?: () => void; title?: string }) {
  const body = <><span className={cn("size-1.5 shrink-0 rounded-full", actor === "user" ? "bg-blue-500" : actor === "agent" ? "bg-brand-500" : "bg-teal-500")} /><span className="truncate">{name}</span></>;
  const cls = "inline-flex max-w-48 items-center gap-1 rounded border border-border bg-background px-1.5 py-0.5 text-[11px]";
  return onClick
    ? <button type="button" title={title} onClick={onClick} className={cn(cls, "hover:border-foreground/30")}>{body}</button>
    : <span title={title} className={cls}>{body}</span>;
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

export const shortDate = (s: string) => new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** Hits per day as bars and the share of scanned traces with a hit as a line. */
export function TrendChart({ series }: { series: DayPoint[] }) {
  if (!series.length) return <p className="flex h-40 items-center justify-center text-xs text-muted-foreground">No data yet.</p>;
  const max = Math.max(1, ...series.map((d) => d.hits));
  const rates = series.map((d) => d.rate ?? 0);
  const maxRate = Math.max(0.01, ...rates);
  const left = 40, right = 860, top = 12, bottom = 160;
  const bw = (right - left) / series.length;
  const y = (n: number) => bottom - (n / max) * (bottom - top);
  const yr = (r: number) => bottom - (r / maxRate) * (bottom - top);
  const ratePoints = series.map((d, i) => d.rate === null ? null : `${left + bw * (i + 0.5)},${yr(d.rate)}`).filter(Boolean).join(" ");
  return <figure className="m-0" aria-label="Behavior trend">
    <svg viewBox="0 0 900 190" className="h-48 w-full" role="img" aria-label="Hits per day and rate of traces with a hit">
      {[0, max / 2, max].map((t) => <g key={t}><line x1={left} x2={right} y1={y(t)} y2={y(t)} stroke="currentColor" opacity={0.08} /><text x={left - 6} y={y(t) + 4} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{Math.round(t)}</text></g>)}
      {series.map((d, i) => <rect key={d.day} x={left + bw * i + bw * 0.15} width={bw * 0.7} y={y(d.hits)} height={bottom - y(d.hits)} className="fill-brand-500/70"><title>{shortDate(d.day)} · {d.hits} hits in {d.traces_with_hit} of {d.traces_scanned} scanned traces</title></rect>)}
      {ratePoints && <polyline points={ratePoints} fill="none" stroke="#2563eb" strokeWidth={1.5} />}
      <text x={left} y={180} fontSize={10} fill="currentColor" opacity={0.55}>{shortDate(series[0].day)}</text>
      <text x={right} y={180} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{shortDate(series.at(-1)!.day)}</text>
      <text x={right + 6} y={top + 4} fontSize={10} fill="#2563eb">{Math.round(maxRate * 100)}%</text>
    </svg>
    <div className="flex gap-4 text-[11px] text-muted-foreground"><span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-sm bg-brand-500/70" />Hits per day</span><span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-3 bg-[#2563eb]" />Share of scanned traces with a hit</span></div>
  </figure>;
}

export function ChangeLabel({ change, current }: { change: number | null; current: number }) {
  if (change === null) return <span className="text-muted-foreground">{current ? "new" : "—"}</span>;
  const pct = Math.round(change * 100);
  return <span className={cn("tabular-nums", pct > 0 ? "text-destructive" : pct < 0 ? "text-success" : "text-muted-foreground")}>{pct > 0 ? "+" : ""}{pct}%</span>;
}

const inputCls = "h-8 w-full rounded-md border border-border bg-transparent px-2 text-xs outline-none focus-visible:border-ring";

export function FieldLabel({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="grid gap-1 text-xs"><span className="font-medium">{label}</span>{children}{hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}</label>;
}

export { inputCls };

/** Create a behavior: model-detected from a definition, or one of the built-in rules. */
export function NewBehaviorDialog({ open, onOpenChange, rules, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; rules: string[]; onCreated: (b: Behavior) => void }) {
  const [name, setName] = useState("");
  const [actor, setActor] = useState<Actor>("agent");
  const [detector, setDetector] = useState<Detector>("llm");
  const [ruleKind, setRuleKind] = useState(rules[0] ?? "");
  const [definition, setDefinition] = useState("");
  const [examples, setExamples] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (!ruleKind && rules.length) setRuleKind(rules[0]); }, [rules, ruleKind]);
  const valid = name.trim() && (detector === "rule" ? !!ruleKind : definition.trim());

  async function submit() {
    setSaving(true);
    try {
      const created = await createBehavior({
        name: name.trim(), actor, detector, definition: definition.trim(),
        examples: examples.split("\n").map((s) => s.trim()).filter(Boolean),
        rule: detector === "rule" ? { kind: ruleKind } : null, severity, enabled: true, alert: null,
      });
      onCreated(created);
      onOpenChange(false);
      setName(""); setDefinition(""); setExamples("");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
    <DialogHeader><DialogTitle>New behavior</DialogTitle><DialogDescription>A named pattern Stash tags on trace windows as traces come in.</DialogDescription></DialogHeader>
    <div className="grid gap-3">
      <FieldLabel label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Refund promised without checking policy" /></FieldLabel>
      <div className="grid grid-cols-3 gap-3">
        <FieldLabel label="Actor"><Select aria-label="Actor" value={actor} onChange={(v) => setActor(v as Actor)} options={ACTORS} /></FieldLabel>
        <FieldLabel label="Detector"><Select aria-label="Detector" value={detector} onChange={(v) => setDetector(v as Detector)} options={[{ value: "llm", label: "Model-detected" }, { value: "rule", label: "Rule" }]} /></FieldLabel>
        <FieldLabel label="Severity"><Select aria-label="Severity" value={severity} onChange={(v) => setSeverity(v as Severity)} options={SEVERITIES.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))} /></FieldLabel>
      </div>
      {detector === "rule" && <FieldLabel label="Rule"><Select aria-label="Rule" value={ruleKind} onChange={setRuleKind} options={rules.map((r) => ({ value: r, label: r.replaceAll("_", " ") }))} /></FieldLabel>}
      <FieldLabel label="Definition" hint={detector === "rule" ? "Optional note; the rule decides what counts." : "What counts, in plain language. The model reads this to tag windows."}>
        <Textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={3} className="text-xs md:text-xs" />
      </FieldLabel>
      {detector === "llm" && <FieldLabel label="Example quotes" hint="One per line. Short excerpts that show the behavior.">
        <Textarea value={examples} onChange={(e) => setExamples(e.target.value)} rows={3} className="text-xs md:text-xs" />
      </FieldLabel>}
    </div>
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={!valid || saving} onClick={() => void submit()}>{saving ? "Creating…" : "Create behavior"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}

export interface TraceWindow { trace_id: string; start_idx: number; end_idx: number }

/** Save trace windows as labeled examples of an existing eval. */
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
      toast.success(`Saved ${res.examples.length} example${res.examples.length === 1 ? "" : "s"} to the eval`);
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
    <DialogHeader><DialogTitle>Save to eval</DialogTitle><DialogDescription>{windows.length} trace window{windows.length === 1 ? "" : "s"} become labeled examples.</DialogDescription></DialogHeader>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {!evals && !error ? <p role="status" className="text-xs text-muted-foreground">Loading evals…</p>
      : !choices.length ? <p className="text-xs text-muted-foreground">No label evals yet. Create one under Evals first.</p>
      : <div className="grid gap-3">
        <FieldLabel label="Eval"><Select aria-label="Eval" value={evalId} onChange={setEvalId} options={choices.map((m) => ({ value: m.id, label: m.name }))} /></FieldLabel>
        <FieldLabel label="Label">{labels.length
          ? <Select aria-label="Label" value={label} onChange={setLabel} options={labels.map((l) => ({ value: l, label: l }))} />
          : <input className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label" />}</FieldLabel>
      </div>}
    <DialogFooter><Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button size="sm" disabled={!evalId || !label || saving || !windows.length} onClick={() => void save()}>{saving ? "Saving…" : "Save examples"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}
