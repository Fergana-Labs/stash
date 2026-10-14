"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowUpRight, Check, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { ActorChip, EnabledSwitch, FieldLabel, SeverityTag, TrendChart, inputCls } from "@/components/behaviors/behavior-ui";
import {
  ACTORS, SEVERITIES, deleteBehavior, getBehavior, getBehaviorOverview, listBehaviorHits, listBehaviors, promoteBehavior, reviewHit,
  stepWindow, traceStepHref, updateBehavior,
  type Actor, type AlertConfig, type Behavior, type BehaviorHit, type BehaviorInput, type BehaviorTrend, type ChannelKind, type Detector, type Severity, type Verdict,
} from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";

type ReviewFilter = Verdict | "unreviewed";
const REVIEW_TABS: { value: ReviewFilter; label: string }[] = [
  { value: "unreviewed", label: "Unreviewed" }, { value: "confirmed", label: "Confirmed" }, { value: "rejected", label: "Rejected" },
];
const PAGE = 50;

export default function BehaviorClient({ id }: { id: string }) {
  const router = useRouter();
  const confirm = useConfirm();
  const [behavior, setBehavior] = useState<Behavior | null>(null);
  const [rules, setRules] = useState<string[]>([]);
  const [trend, setTrend] = useState<BehaviorTrend | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");
  useBreadcrumbs([{ label: "Behaviors", href: "/reward-models/behaviors" }, { label: behavior?.name ?? "Behavior" }], `behavior-${id}-${behavior?.name ?? ""}`);

  const load = useCallback(async () => {
    try {
      const [b, list] = await Promise.all([getBehavior(id), listBehaviors()]);
      setBehavior(b);
      setRules(list.rules);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    let cancelled = false;
    getBehaviorOverview(days).then((o) => { if (!cancelled) setTrend(o.behaviors.find((t) => t.behavior.id === id) ?? null); })
      .catch((e) => { if (!cancelled) toast.error(errorMessage(e)); });
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
      router.push("/reward-models/behaviors");
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

  return <EvalPageFrame title={behavior.name} description={behavior.definition || undefined}
    actions={<div className="flex items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><EnabledSwitch checked={behavior.enabled} label="Monitor this behavior" onChange={(enabled) => void patch({ enabled }, enabled ? "Monitoring on" : "Monitoring off")} />{behavior.enabled ? "Monitoring" : "Paused"}</span>
      {behavior.eval_id
        ? <Button size="sm" variant="outline" asChild><Link href={`/reward-models/evals/${behavior.eval_id}`}>Open eval<ArrowUpRight /></Link></Button>
        : <Button size="sm" variant="outline" onClick={() => void promote()}>Promote to eval</Button>}
      <Button size="sm" variant="ghost" aria-label="Delete behavior" title="Delete behavior" onClick={() => void remove()}><Trash2 /></Button>
    </div>}>
    <div className="mb-5 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <ActorChip actor={behavior.actor} /><SeverityTag severity={behavior.severity} />
      <span>{behavior.detector === "rule" ? `Rule: ${behavior.rule?.kind.replaceAll("_", " ")}` : behavior.detector === "agent_judge" ? "Agent judge" : "Model-detected"}</span>
      <span>v{behavior.version}</span>
      {behavior.last_alert_at && <span>Last alert {relativeTime(behavior.last_alert_at)}</span>}
    </div>

    <section className="mb-6 rounded border border-border p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <div><h2 className="text-sm font-semibold">Trend</h2>{trend && <p className="mt-0.5 text-xs text-muted-foreground">{trend.last_7_days} hits in the last 7 days · {trend.previous_7_days} the week before · {trend.traces_scanned} traces scanned in range</p>}</div>
        <Select aria-label="Time range" value={String(days)} onChange={(v) => setDays(Number(v))} options={[{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }]} className="h-8 w-36 text-xs" />
      </header>
      <TrendChart series={trend?.series ?? []} />
    </section>

    <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <DefinitionForm key={`${behavior.id}-${behavior.updated_at}`} behavior={behavior} rules={rules} onSave={patch} />
      <AlertForm key={`alert-${behavior.updated_at}`} alert={behavior.alert} onSave={(alert) => patch({ alert }, alert ? "Alert saved" : "Alert removed")} />
    </div>

    <HitQueue behaviorId={id} />
  </EvalPageFrame>;
}

function DefinitionForm({ behavior, rules, onSave }: { behavior: Behavior; rules: string[]; onSave: (changes: Partial<BehaviorInput>, success?: string) => Promise<boolean> }) {
  const [name, setName] = useState(behavior.name);
  const [actor, setActor] = useState<Actor>(behavior.actor);
  const [detector, setDetector] = useState<Detector>(behavior.detector);
  const [ruleKind, setRuleKind] = useState(behavior.rule?.kind ?? rules[0] ?? "");
  const [definition, setDefinition] = useState(behavior.definition);
  const [examples, setExamples] = useState(behavior.examples.join("\n"));
  const [severity, setSeverity] = useState<Severity>(behavior.severity);
  const [saving, setSaving] = useState(false);
  const confirm = useConfirm();

  const exampleList = examples.split("\n").map((s) => s.trim()).filter(Boolean);
  const rule = detector === "rule" ? { kind: ruleKind } : null;
  const changes: Partial<BehaviorInput> = {
    ...(name.trim() !== behavior.name && { name: name.trim() }),
    ...(actor !== behavior.actor && { actor }),
    ...(severity !== behavior.severity && { severity }),
    ...(detector !== behavior.detector && { detector }),
    ...((rule?.kind ?? null) !== (behavior.rule?.kind ?? null) && { rule }),
    ...(definition.trim() !== behavior.definition && { definition: definition.trim() }),
    ...(JSON.stringify(exampleList) !== JSON.stringify(behavior.examples) && { examples: exampleList }),
  };
  const dirty = Object.keys(changes).length > 0;
  const changesMeaning = ["definition", "examples", "detector", "rule"].some((k) => k in changes);
  const detectors: { value: Detector; label: string }[] = [
    { value: "llm", label: "Model-detected" }, { value: "rule", label: "Rule" },
    ...(behavior.detector === "agent_judge" ? [{ value: "agent_judge" as Detector, label: "Agent judge" }] : []),
  ];

  async function save() {
    if (changesMeaning && !await confirm({
      title: "Rescan with the new definition?",
      body: "Changing what this behavior means rescans your traces. Hits nobody reviewed yet are dropped and found again; confirmed and rejected hits are kept.",
      confirmLabel: "Save and rescan", destructive: false,
    })) return;
    setSaving(true);
    await onSave(changes, changesMeaning ? "Saved; rescanning traces" : "Saved");
    setSaving(false);
  }

  return <section className="rounded border border-border p-4">
    <h2 className="mb-3 text-sm font-semibold">Definition</h2>
    <div className="grid gap-3">
      <FieldLabel label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></FieldLabel>
      <div className="grid grid-cols-3 gap-3">
        <FieldLabel label="Actor"><Select aria-label="Actor" value={actor} onChange={(v) => setActor(v as Actor)} options={ACTORS} /></FieldLabel>
        <FieldLabel label="Detector"><Select aria-label="Detector" value={detector} onChange={(v) => setDetector(v as Detector)} options={detectors} /></FieldLabel>
        <FieldLabel label="Severity"><Select aria-label="Severity" value={severity} onChange={(v) => setSeverity(v as Severity)} options={SEVERITIES.map((s) => ({ value: s, label: s[0].toUpperCase() + s.slice(1) }))} /></FieldLabel>
      </div>
      {detector === "rule" && <FieldLabel label="Rule"><Select aria-label="Rule" value={ruleKind} onChange={setRuleKind} options={rules.map((r) => ({ value: r, label: r.replaceAll("_", " ") }))} /></FieldLabel>}
      <FieldLabel label="Definition"><Textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={4} className="text-xs md:text-xs" /></FieldLabel>
      {detector !== "rule" && <FieldLabel label="Example quotes" hint="One per line."><Textarea value={examples} onChange={(e) => setExamples(e.target.value)} rows={3} className="text-xs md:text-xs" /></FieldLabel>}
      {changesMeaning && <p className="text-[11px] text-amber-700 dark:text-amber-400">Saving changes the behavior’s meaning: traces are rescanned and unreviewed hits are dropped.</p>}
      <div><Button size="sm" disabled={!dirty || saving || !name.trim()} onClick={() => void save()}>{saving ? "Saving…" : "Save changes"}</Button></div>
    </div>
  </section>;
}

function AlertForm({ alert, onSave }: { alert: AlertConfig | null; onSave: (alert: AlertConfig | null) => Promise<boolean> }) {
  const [on, setOn] = useState(alert !== null);
  const [threshold, setThreshold] = useState(String(alert?.threshold ?? 5));
  const [windowHours, setWindowHours] = useState(String(alert?.window_hours ?? 24));
  const [cooldown, setCooldown] = useState(String(alert?.cooldown_hours ?? 24));
  const [channels, setChannels] = useState<ChannelKind[]>(alert?.channels ?? ["slack", "email"]);
  const [saving, setSaving] = useState(false);
  const valid = Number(threshold) >= 1 && Number(windowHours) >= 1 && Number(windowHours) <= 720 && Number(cooldown) >= 1 && Number(cooldown) <= 720;

  async function save() {
    setSaving(true);
    await onSave(on ? { threshold: Number(threshold), window_hours: Number(windowHours), cooldown_hours: Number(cooldown), channels } : null);
    setSaving(false);
  }

  return <section className="rounded border border-border p-4">
    <header className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Alert</h2><EnabledSwitch checked={on} label="Alert on this behavior" onChange={setOn} /></header>
    {on ? <div className="grid gap-3">
      <div className="grid grid-cols-3 gap-3">
        <FieldLabel label="Threshold" hint="hits"><input type="number" min={1} className={inputCls} value={threshold} onChange={(e) => setThreshold(e.target.value)} /></FieldLabel>
        <FieldLabel label="Window" hint="hours"><input type="number" min={1} max={720} className={inputCls} value={windowHours} onChange={(e) => setWindowHours(e.target.value)} /></FieldLabel>
        <FieldLabel label="Cooldown" hint="hours"><input type="number" min={1} max={720} className={inputCls} value={cooldown} onChange={(e) => setCooldown(e.target.value)} /></FieldLabel>
      </div>
      <fieldset className="flex gap-4 text-xs"><legend className="mb-1 font-medium">Channels</legend>
        {(["slack", "email"] as ChannelKind[]).map((c) => <label key={c} className="inline-flex items-center gap-1.5 capitalize"><input type="checkbox" checked={channels.includes(c)} onChange={(e) => setChannels((cur) => e.target.checked ? [...cur, c] : cur.filter((x) => x !== c))} />{c}</label>)}
      </fieldset>
      <p className="text-[11px] text-muted-foreground">Notify when this behavior happens {threshold || "N"}+ times within {windowHours || "N"}h, at most once every {cooldown || "N"}h.</p>
    </div> : <p className="text-xs text-muted-foreground">No alert. Turn it on to be notified on Slack or email when hits spike.</p>}
    <div className="mt-3"><Button size="sm" variant="outline" disabled={saving || (on && (!valid || !channels.length)) || (!on && alert === null)} onClick={() => void save()}>{saving ? "Saving…" : "Save alert"}</Button></div>
  </section>;
}

function HitQueue({ behaviorId }: { behaviorId: string }) {
  const [filter, setFilter] = useState<ReviewFilter>("unreviewed");
  const [hits, setHits] = useState<BehaviorHit[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (offset = 0) => {
    try {
      const page = (await listBehaviorHits(behaviorId, { review: filter, limit: PAGE, offset })).hits;
      setHits((cur) => offset ? [...(cur ?? []), ...page] : page);
      setMore(page.length === PAGE);
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [behaviorId, filter]);
  useEffect(() => { setHits(null); void load(); }, [load]);

  async function review(hit: BehaviorHit, verdict: Verdict | null) {
    setBusy(hit.id);
    try {
      await reviewHit(hit.id, verdict);
      setHits((cur) => cur?.filter((h) => h.id !== hit.id) ?? cur);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return <section>
    <header className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold">Hits</h2>
      <nav aria-label="Review status" className="flex gap-1 text-xs">{REVIEW_TABS.map((t) => <button key={t.value} type="button" aria-pressed={filter === t.value} onClick={() => setFilter(t.value)}
        className={cn("rounded-md px-2 py-1", filter === t.value ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>{t.label}</button>)}</nav>
    </header>
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
    <ul className="divide-y divide-border rounded border border-border">
      {hits?.map((hit) => <li key={hit.id} className="grid gap-2 px-4 py-3 text-xs">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Link href={traceStepHref(hit.trace_id, hit.start_idx)} className="font-medium hover:underline">{hit.trace_title || "Untitled trace"}</Link>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{stepWindow(hit.start_idx, hit.end_idx)}{hit.trace_created_at && ` · ${relativeTime(hit.trace_created_at)}`}{hit.source === "human" && " · tagged by hand"}{hit.confidence != null && hit.source !== "human" && ` · ${Math.round(hit.confidence * 100)}% confidence`}</p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            {hit.review !== "confirmed" && <Button size="xs" variant="outline" disabled={busy === hit.id} onClick={() => void review(hit, "confirmed")}><Check />Confirm</Button>}
            {hit.review !== "rejected" && <Button size="xs" variant="outline" disabled={busy === hit.id} onClick={() => void review(hit, "rejected")}><X />Reject</Button>}
            {hit.review && <Button size="xs" variant="ghost" disabled={busy === hit.id} onClick={() => void review(hit, null)}>Undo</Button>}
          </div>
        </div>
        {!!hit.evidence?.length && <ul className="grid gap-1">{hit.evidence.map((ev, i) => <li key={i} className="border-l-2 border-brand-500/40 pl-2 text-muted-foreground"><span className="mr-1.5 text-[10.5px] tabular-nums">step {ev.idx + 1}</span>“{ev.quote}”</li>)}</ul>}
        {hit.note && <p className="text-muted-foreground">{hit.note}</p>}
      </li>)}
      {!hits && !error && <li className="px-4 py-6 text-xs"><span role="status" className="text-muted-foreground">Loading hits…</span></li>}
      {hits && !hits.length && <li className="px-4 py-8 text-xs text-muted-foreground">{filter === "unreviewed" ? "Nothing to review." : `No ${filter} hits.`}</li>}
    </ul>
    {more && <div className="mt-2"><Button size="sm" variant="ghost" onClick={() => void load(hits?.length ?? 0)}>Load more</Button></div>}
  </section>;
}
