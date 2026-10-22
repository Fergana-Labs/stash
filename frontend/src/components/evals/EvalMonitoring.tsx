"use client";

import { useCallback, useEffect, useState } from "react";
import { Select } from "@/components/ui/select";
import { errorMessage } from "@/components/reward-models/rm-text";
import { value } from "@/components/monitoring/RollingRewardChart";
import { evalSurfaceClass } from "./eval-ui";
import { OutcomeLink } from "./EvalComposition";
import { AlertTriangle, Layers } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { imMonitoring, imSetAlert, imStartRefine, type Monitoring } from "@/lib/intuition-api";

// Buckets are calendar days (YYYY-MM-DD); parse them as local dates, not UTC midnight.
const date = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const percent = (n: number | null | undefined) => n == null ? "—" : `${Math.round(n * 100)}%`;
const RANGES = [{ value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }];

/** Live quality of a saved eval: volume, accuracy against feedback, calibration, drift, misses. */
export default function EvalMonitoring({ id, onOpenCall, onImprove }: { id: string; onOpenCall?: (predictionId: string) => void; onImprove?: () => void }) {
  const [days, setDays] = useState("30");
  const [data, setData] = useState<Monitoring | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => { setError(""); setData(await imMonitoring(id, Number(days))); }, [id, days]);
  useEffect(() => { void load().catch((e) => setError(errorMessage(e))); }, [load]);
  if (error) return <p role="alert" className="text-xs text-destructive">{error}</p>;
  if (!data) return <p role="status" className="text-xs text-muted-foreground">Loading monitoring…</p>;
  const s = data.summary;
  return <section aria-label="Eval monitoring" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-sm font-semibold">Monitoring</h2><p className="text-xs text-muted-foreground">Accuracy and calibration count only calls that received feedback — a correction, an outcome, or a downstream verdict.</p></div>
      <Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label="Monitoring range" value={days} onChange={setDays} options={RANGES} className="h-8 w-36 px-3 text-xs" />
    </div>
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <Stat label="Calls" value={String(s.calls)} detail={s.errors ? `${s.errors} failed` : "none failed"} />
      <Stat label="With feedback" value={String(s.with_feedback)} detail={s.calls ? `${percent(s.with_feedback / Math.max(1, s.calls - s.errors))} of decisions` : "—"} />
      <Stat label="Accuracy" value={percent(s.accuracy)} detail={s.with_feedback ? `on ${s.with_feedback} calls` : "needs feedback"} />
      <Stat label="Calibration error" value={s.ece == null ? "—" : value(s.ece)} detail="lower is better" />
      <Stat label="Mean outcome" value={s.mean_value == null ? "—" : value(s.mean_value)} detail="from feedback values" />
    </div>
    {data.refine_suggested && <StaleBanner id={id} reason={data.refine_reason ?? null} onImprove={onImprove} />}
    <AgreementAlert id={id} />
    {data.truncated && <p className="text-xs text-muted-foreground">Only the most recent calls in this range are included.</p>}
    {!data.daily.length ? <p className="rounded border border-border px-4 py-10 text-center text-xs text-muted-foreground">No calls in this range. Calls from the sandbox and the API appear here.</p> : <>
      <div className="grid gap-4 lg:grid-cols-2">
        <DailyBars data={data} />
        <DailyAccuracy data={data} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Reliability bins={s.reliability} />
        <Drift drift={data.drift} />
      </div>
      <Versions data={data} />
      <OutcomeLink id={id} />
      <Disagreements data={data} onOpenCall={onOpenCall} />
    </>}
  </section>;
}

/** The rubric may be going stale: say why and offer to improve it. */
function StaleBanner({ id, reason, onImprove }: { id: string; reason: string | null; onImprove?: () => void }) {
  const [starting, setStarting] = useState(false);
  async function improve() {
    setStarting(true);
    try {
      await imStartRefine(id);
      toast.success("Improving the rubric; follow it under Build eval");
      onImprove?.();
    } catch (e) { toast.error(errorMessage(e)); } finally { setStarting(false); }
  }
  return <div role="status" className="flex flex-wrap items-center gap-3 rounded border border-amber-500/40 bg-amber-500/8 px-3 py-2 text-xs">
    <AlertTriangle className="size-4 shrink-0 text-amber-600" />
    <span className="min-w-0 flex-1">This rubric may be going stale{reason ? `: ${reason}` : "."}</span>
    <Button size="xs" variant="outline" disabled={starting} onClick={() => void improve()}><Layers />{starting ? "Starting…" : "Improve rubric"}</Button>
  </div>;
}

/** Write-mostly: the eval detail may not echo the alert back, so this shows what was last saved here. */
function AgreementAlert({ id }: { id: string }) {
  const [threshold, setThreshold] = useState("80");
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function save(on: boolean) {
    setSaving(true);
    try {
      await imSetAlert(id, on ? { min_agreement: Number(threshold) / 100, channels: ["slack", "email"] } : null);
      setSaved(on ? threshold : "off");
      toast.success(on ? `Alert set: agreement below ${threshold}%` : "Alert off");
    } catch (e) { toast.error(errorMessage(e)); } finally { setSaving(false); }
  }
  const valid = Number(threshold) > 0 && Number(threshold) <= 100;
  return <div className="flex flex-wrap items-center gap-2 text-xs">
    <span>Alert me when agreement with production feedback drops below</span>
    <input type="number" min={1} max={100} aria-label="Agreement threshold" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="h-7 w-14 rounded-md border border-border bg-transparent px-1.5 text-right tabular-nums" />%
    <Button size="xs" variant="outline" disabled={saving || !valid} onClick={() => void save(true)}>{saved && saved !== "off" ? "Update" : "Set alert"}</Button>
    {saved && saved !== "off" && <Button size="xs" variant="ghost" disabled={saving} onClick={() => void save(false)}>Turn off</Button>}
    {saved && <span className="text-muted-foreground">{saved === "off" ? "Off" : `On · below ${saved}% · Slack and email`}</span>}
  </div>;
}

function Stat({ label, value: shown, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded border border-border p-3"><div className="text-[11px] text-muted-foreground">{label}</div><div className="mt-1 text-lg font-semibold tabular-nums">{shown}</div><div className="text-[11px] text-muted-foreground">{detail}</div></div>;
}

function Panel({ title, caption, children }: { title: string; caption: string; children: React.ReactNode }) {
  return <figure className="m-0 space-y-2 rounded border border-border p-4"><figcaption><span className="block text-sm font-medium">{title}</span><span className="block text-xs text-muted-foreground">{caption}</span></figcaption>{children}</figure>;
}

const W = 420, H = 150, L = 34, R = 8, T = 10, B = 22;
const xAt = (i: number, n: number) => L + (n <= 1 ? (W - L - R) / 2 : i / (n - 1) * (W - L - R));

function DailyBars({ data }: { data: Monitoring }) {
  const days = data.daily;
  const max = Math.max(1, ...days.map((d) => d.calls));
  const y = (n: number) => H - B - n / max * (H - B - T);
  const slot = (W - L - R) / days.length;
  const bar = Math.max(2, Math.min(24, slot - 2));
  return <Panel title="Calls per day" caption="Every logged call, including failed ones.">
    <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img" aria-label="Calls per day">
      {[0, max].map((tick) => <g key={tick}><line x1={L} x2={W - R} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.1} /><text x={L - 6} y={y(tick) + 4} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{tick}</text></g>)}
      {days.map((d, i) => { const x = L + i * slot + (slot - bar) / 2; return <g key={d.date}>
        <rect x={x} y={y(d.calls)} width={bar} height={Math.max(0, y(0) - y(d.calls))} rx={Math.min(4, bar / 2)} className="fill-primary" opacity={0.8} />
        <rect x={L + i * slot} y={T} width={slot} height={H - B - T} fill="transparent"><title>{date(d.date)} · {d.calls} calls · {d.errors} failed · {d.with_feedback} with feedback</title></rect>
      </g>; })}
      <text x={L} y={H - 6} fontSize={10} fill="currentColor" opacity={0.55}>{date(days[0].date)}</text>
      <text x={W - R} y={H - 6} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{date(days.at(-1)!.date)}</text>
    </svg>
    <Measurements headers={["Day", "Calls", "Failed", "With feedback"]} rows={days.map((d) => [date(d.date), d.calls, d.errors, d.with_feedback])} />
  </Panel>;
}

function DailyAccuracy({ data }: { data: Monitoring }) {
  const days = data.daily.filter((d) => d.accuracy != null);
  const y = (n: number) => H - B - n * (H - B - T);
  return <Panel title="Accuracy per day" caption="Share of fed-back calls where the eval matched the feedback label.">
    {!days.length ? <p className="flex h-40 items-center justify-center text-xs text-muted-foreground">No feedback yet. Correct a call or send an outcome to measure accuracy.</p> :
      <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img" aria-label="Accuracy per day">
        {[0, 0.5, 1].map((tick) => <g key={tick}><line x1={L} x2={W - R} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.1} /><text x={L - 6} y={y(tick) + 4} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{percent(tick)}</text></g>)}
        <polyline points={days.map((d, i) => `${xAt(i, days.length)},${y(d.accuracy!)}`).join(" ")} className="stroke-primary" strokeWidth={2} fill="none" />
        {days.map((d, i) => <g key={d.date}><circle cx={xAt(i, days.length)} cy={y(d.accuracy!)} r={4} className="fill-primary stroke-background" strokeWidth={2} /><circle cx={xAt(i, days.length)} cy={y(d.accuracy!)} r={12} fill="transparent"><title>{date(d.date)} · {percent(d.accuracy)} of {d.with_feedback} calls</title></circle></g>)}
        <text x={L} y={H - 6} fontSize={10} fill="currentColor" opacity={0.55}>{date(days[0].date)}</text>
        <text x={W - R} y={H - 6} fontSize={10} textAnchor="end" fill="currentColor" opacity={0.55}>{date(days.at(-1)!.date)}</text>
      </svg>}
    {!!days.length && <Measurements headers={["Day", "Accuracy", "Calls with feedback"]} rows={days.map((d) => [date(d.date), percent(d.accuracy), d.with_feedback])} />}
  </Panel>;
}

function Reliability({ bins }: { bins: Monitoring["summary"]["reliability"] }) {
  const S = 150, P = 26;
  const at = (n: number) => P + n * (S - P - 6);
  const atY = (n: number) => S - P - n * (S - P - 6);
  return <Panel title="Calibration" caption="When the eval says 80% confident, it should be right about 80% of the time. Points on the diagonal are well calibrated.">
    {!bins.length ? <p className="flex h-40 items-center justify-center text-xs text-muted-foreground">Needs calls with feedback.</p> : <div className="flex flex-wrap items-start gap-4">
      <svg viewBox={`0 0 ${S} ${S}`} className="h-40 w-40 shrink-0" role="img" aria-label="Confidence versus observed accuracy">
        <rect x={at(0)} y={atY(1)} width={at(1) - at(0)} height={atY(0) - atY(1)} fill="none" stroke="currentColor" opacity={0.15} />
        <line x1={at(0)} y1={atY(0)} x2={at(1)} y2={atY(1)} stroke="currentColor" opacity={0.3} strokeDasharray="3 3" />
        {bins.map((b) => <circle key={b.bin} cx={at(b.confidence)} cy={atY(b.accuracy)} r={Math.min(9, 3 + Math.sqrt(b.n))} className="fill-primary stroke-background" strokeWidth={2} opacity={0.85}><title>{percent(b.confidence)} confident · {percent(b.accuracy)} correct · {b.n} calls</title></circle>)}
        <text x={at(0.5)} y={S - 6} fontSize={9} textAnchor="middle" fill="currentColor" opacity={0.55}>Confidence</text>
        <text x={8} y={atY(0.5)} fontSize={9} textAnchor="middle" fill="currentColor" opacity={0.55} transform={`rotate(-90 8 ${atY(0.5)})`}>Correct</text>
      </svg>
      <Measurements open headers={["Confidence", "Correct", "Calls"]} rows={bins.map((b) => [percent(b.confidence), percent(b.accuracy), b.n])} />
    </div>}
  </Panel>;
}

function Drift({ drift }: { drift: Monitoring["drift"] }) {
  if (!drift) return <Panel title="Drift" caption="Compares recent calls with the examples the saved eval learned from."><p className="text-xs text-muted-foreground">Save the eval to compare its recent calls with its training examples.</p></Panel>;
  const maxShift = Math.max(0.01, ...drift.features.map((f) => Math.abs(f.shift)));
  return <Panel title="Drift" caption={`Last ${drift.window_days} days of v${drift.version ?? "?"} (${drift.recent_calls} calls) vs its ${drift.train_examples ?? 0} training examples.`}>
    {!drift.recent_calls ? <p className="text-xs text-muted-foreground">No recent calls from the saved version.</p> : <>
      <table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-1.5 font-medium">Decision</th><th className="text-right font-medium">Training share</th><th className="text-right font-medium">Recent share</th></tr></thead>
        <tbody>{drift.labels.map((row) => <tr key={row.label} className="border-b border-border/60"><td className="py-1.5">{row.label}</td><td className="text-right tabular-nums">{percent(row.train_share)}</td><td className="text-right tabular-nums">{percent(row.recent_share)}</td></tr>)}</tbody></table>
      <div className="space-y-1.5"><div className="text-[11px] font-medium text-muted-foreground">Largest changes in criteria answers</div>
        {drift.features.map((f) => <div key={f.feature} className="grid grid-cols-[minmax(0,1fr)_120px_52px] items-center gap-2 text-[11px]" title={`Training mean ${value(f.train_mean)} → recent ${value(f.recent_mean)}`}>
          <span className="truncate">{f.feature}</span>
          <span className="relative h-2 rounded-full bg-border/60"><span className="absolute top-0 h-2 w-px bg-foreground/40" style={{ left: "50%" }} /><span className="absolute top-0 h-2 rounded-full bg-primary" style={{ left: f.shift < 0 ? `${50 - Math.abs(f.shift) / maxShift * 50}%` : "50%", width: `${Math.abs(f.shift) / maxShift * 50}%` }} /></span>
          <span className="text-right tabular-nums">{f.shift > 0 ? "+" : ""}{value(f.shift)}</span>
        </div>)}
      </div>
    </>}
  </Panel>;
}

function Versions({ data }: { data: Monitoring }) {
  return <section aria-label="Versions in use" className="overflow-hidden rounded border border-border">
    <h3 className="px-4 py-3 text-sm font-medium">By version</h3>
    <table className="w-full text-left text-xs"><thead className="bg-surface text-muted-foreground"><tr className="h-8 [&>th]:px-4 [&>th]:font-medium"><th>Version</th><th className="text-right">Calls</th><th className="text-right">Failed</th><th className="text-right">With feedback</th><th className="text-right">Accuracy</th><th className="text-right">Calibration error</th></tr></thead>
      <tbody>{data.versions.map((v) => <tr key={v.version} className="h-9 border-t border-border [&>td]:px-4"><td>v{v.version}</td><td className="text-right tabular-nums">{v.calls}</td><td className="text-right tabular-nums">{v.errors}</td><td className="text-right tabular-nums">{v.with_feedback}</td><td className="text-right tabular-nums">{percent(v.accuracy)}</td><td className="text-right tabular-nums">{v.ece == null ? "—" : value(v.ece)}</td></tr>)}</tbody></table>
  </section>;
}

function Disagreements({ data, onOpenCall }: { data: Monitoring; onOpenCall?: (predictionId: string) => void }) {
  return <section aria-label="Disagreements" className="overflow-hidden rounded border border-border">
    <div className="px-4 py-3"><h3 className="text-sm font-medium">Where the eval was wrong <span className="font-normal text-muted-foreground">({data.disagreements.length})</span></h3><p className="text-xs text-muted-foreground">Calls whose feedback disagrees with the decision, and the criterion that pushed hardest toward it.</p></div>
    {!data.disagreements.length ? <p className="border-t border-border px-4 py-6 text-center text-xs text-muted-foreground">No disagreements with feedback in this range.</p> :
      <ul className="divide-y divide-border border-t border-border">{data.disagreements.map((d) => <li key={d.prediction_id}>
        <button className="grid w-full gap-1 px-4 py-2.5 text-left text-xs hover:bg-surface disabled:cursor-default" disabled={!onOpenCall} onClick={() => onOpenCall?.(d.prediction_id)}>
          <span className="line-clamp-1">{d.preview}</span>
          <span className="flex flex-wrap gap-3 text-muted-foreground"><span>Eval: <strong className="text-foreground">{d.predicted}</strong> ({percent(d.confidence)})</span><span>Feedback: <strong className="text-foreground">{d.truth}</strong> from {d.truth_source}</span>{d.top_feature && <span>Driven by {d.top_feature.feature}</span>}{d.ref && <span>ref {d.ref}</span>}<span>v{d.version} · {new Date(d.created_at).toLocaleString()}</span></span>
        </button>
      </li>)}</ul>}
  </section>;
}

function Measurements({ headers, rows, open = false }: { headers: string[]; rows: (string | number)[][]; open?: boolean }) {
  return <details className="text-xs" open={open}><summary className="cursor-pointer text-muted-foreground">{open ? "Measurements" : "View chart measurements"}</summary><div className="mt-2 max-h-48 overflow-auto"><table className="w-full text-left"><thead><tr className="border-b border-border text-muted-foreground">{headers.map((h, i) => <th key={h} className={`py-1.5 font-medium ${i ? "pl-4 text-right" : ""}`}>{h}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={String(row[0])} className="border-b border-border/60">{row.map((cell, i) => <td key={i} className={`py-1.5 ${i ? "pl-4 text-right tabular-nums" : ""}`}>{cell}</td>)}</tr>)}</tbody></table></div></details>;
}
