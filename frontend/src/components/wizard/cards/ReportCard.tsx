"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart3, RefreshCw, Rocket, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import ReliabilityChart from "@/components/intuitions/ReliabilityChart";
import DifficultyChart from "@/components/intuitions/DifficultyChart";
import ClassificationTable, { classificationFromRows } from "@/components/intuitions/ClassificationTable";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imPromote } from "@/lib/intuition-api";
import { wzReport, wzTrain, type TrainingReport } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, pct, Stat, useWizard } from "../wizard-ui";

const KIND_LABEL = { verdict: "zero-shot", probe: "probe", criterion: "criterion" } as const;

/** Held-out accuracy by number of labels, with zero-shot Jev as the dashed baseline. */
export function LearningCurve({ curve, baseline }: { curve: TrainingReport["learning_curve"]; baseline: number | null }) {
  if (curve.length < 2) return <p className="m-0 text-[12px] text-muted-foreground">Label a few more examples to see the learning curve.</p>;
  const W = 300, H = 130, P = { l: 30, r: 8, t: 8, b: 22 };
  const maxN = Math.max(...curve.map((c) => c.n));
  const x = (n: number) => P.l + (Math.log2(n) / Math.log2(Math.max(maxN, 2))) * (W - P.l - P.r);
  const lo = Math.min(0.4, ...curve.map((c) => c.accuracy), baseline ?? 1);
  const y = (a: number) => P.t + (1 - (a - lo) / (1 - lo)) * (H - P.t - P.b);
  const path = curve.map((c, i) => `${i ? "L" : "M"}${x(c.n).toFixed(1)},${y(c.accuracy).toFixed(1)}`).join(" ");
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[360px]" role="img" aria-label="Learning curve: held-out accuracy by number of labeled examples">
        {[lo, (lo + 1) / 2, 1].map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={0.5} />
            <text x={P.l - 4} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground font-mono text-[8px]">{Math.round(t * 100)}%</text>
          </g>
        ))}
        {baseline != null && <line x1={P.l} x2={W - P.r} y1={y(baseline)} y2={y(baseline)} className="stroke-muted-foreground" strokeDasharray="3 3" strokeWidth={0.9} />}
        <path d={path} fill="none" className="stroke-brand-500" strokeWidth={1.75} />
        {curve.map((c) => (
          <g key={c.n}>
            <title>{`${c.n} labels: ${pct(c.accuracy)} held-out accuracy (mean of ${c.draws} draws)`}</title>
            <circle cx={x(c.n)} cy={y(c.accuracy)} r={2.6} className="fill-brand-500" />
            <text x={x(c.n)} y={H - 8} textAnchor="middle" className="fill-muted-foreground font-mono text-[8px]">{c.n}</text>
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] text-muted-foreground">Held-out accuracy vs. labels used{baseline != null ? "; dashed = zero-shot Jev" : ""}.</figcaption>
    </figure>
  );
}

export default function ReportCard() {
  const { modelId, send, refresh, version } = useWizard();
  const [report, setReport] = useState<TrainingReport | null | undefined>(undefined);
  const [busy, setBusy] = useState<"" | "train" | "ship">("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try { setReport((await wzReport(modelId)).report); } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  if (!modelId) return <CardShell icon={BarChart3} title="Training report"><NeedsModel /></CardShell>;

  async function retrain() {
    if (!modelId) return;
    setBusy("train"); setError("");
    try {
      const r = await wzTrain(modelId);
      setReport(r); refresh();
      send(`Retrained: ${pct(r.holdout.accuracy)} held-out accuracy on ${r.holdout.n} examples.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

  async function ship() {
    if (!modelId || !report) return;
    setBusy("ship"); setError("");
    try {
      const detail = await imPromote(modelId, !report.gate.passed);
      refresh();
      send(`Shipped version ${detail.active?.number ?? ""} as the live model${report.gate.passed ? "" : " (overriding the gate)"}.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

  const zeroShot = report?.leaderboard.find((r) => r.name === "Jev zero-shot")?.accuracy ?? null;
  const fused = report?.holdout.accuracy ?? null;
  const lift = fused != null && zeroShot != null ? fused - zeroShot : null;
  // The report may carry head.classification; otherwise derive it from the held-out rows.
  const classification = report ? report.holdout.classification ?? classificationFromRows(report.holdout.rows, Object.keys(report.counts.labels)) : null;

  return (
    <CardShell
      icon={BarChart3}
      title="Training report"
      subtitle={report ? `Version ${report.version} · ${report.counts.train} training, ${report.counts.held_out} held-out` : undefined}
      actions={<Button size="xs" variant="ghost" disabled={!!busy} onClick={() => void retrain()}><RefreshCw className={cn(busy === "train" && "animate-spin")} />{busy === "train" ? "Training…" : "Retrain"}</Button>}
    >
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {report === undefined && <p className="m-0 text-[12px] text-muted-foreground">Loading…</p>}
      {report === null && <p className="m-0 text-[12px] text-muted-foreground">Not trained yet. Ask the wizard to train, or press Retrain.</p>}
      {report && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Held-out accuracy" value={pct(fused)} hint={report.holdout.accuracy_interval ? `95% CI ${pct(report.holdout.accuracy_interval[0])}–${pct(report.holdout.accuracy_interval[1])}` : `${report.holdout.n} examples`} />
            <Stat label="vs. zero-shot" value={lift == null ? "—" : `${lift >= 0 ? "+" : ""}${Math.round(lift * 100)} pts`} tone={lift == null ? undefined : lift > 0 ? "good" : lift < 0 ? "bad" : undefined} hint={zeroShot != null ? `Jev alone: ${pct(zeroShot)}` : undefined} />
            <Stat label="Cross-validated" value={pct(report.cross_validated?.accuracy)} hint={report.cross_validated?.n ? `on ${report.cross_validated.n} training labels` : "needs more labels"} />
            <Stat label="Gate" value={report.gate.passed ? "Pass" : "Blocked"} tone={report.gate.passed ? "good" : "bad"} hint={report.gate.active_version ? `vs. live v${report.gate.active_version}` : "first version"} />
          </div>

          {report.gate.active_version != null && (
            <p className="m-0 text-[12px]">
              Compared with live v{report.gate.active_version}: <b className="text-emerald-700 dark:text-emerald-400">fixed {report.gate.fixes?.length ?? 0}</b>, <b className={(report.gate.flips?.length ?? 0) ? "text-red-600 dark:text-red-400" : undefined}>broke {report.gate.flips?.length ?? 0}</b>
              {report.gate.pinned && report.gate.pinned.n > 0 && <>, pinned cases {Math.round((report.gate.pinned.accuracy ?? 0) * report.gate.pinned.n)}/{report.gate.pinned.n} pass</>}.
            </p>
          )}
          {report.gate.active_version == null && report.gate.pinned && report.gate.pinned.n > 0 && (
            <p className="m-0 text-[12px]">Pinned cases: {Math.round((report.gate.pinned.accuracy ?? 0) * report.gate.pinned.n)}/{report.gate.pinned.n} pass.</p>
          )}

          {report.warnings.map((w) => <p key={w} className="m-0 rounded-md border border-yellow-500/30 bg-yellow-500/8 px-2.5 py-1.5 text-[11.5px] text-yellow-900 dark:text-yellow-200">{w}</p>)}

          <section>
            <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Held-out leaderboard</h4>
            <div className="space-y-1.5">
              {report.leaderboard.map((row) => (
                <div key={row.name} className="grid grid-cols-[9rem_1fr_3.5rem] items-center gap-2.5" title={row.detail}>
                  <span className={cn("truncate text-[12px]", row.shipping ? "font-semibold" : "text-dim")}>{row.name}</span>
                  <div className="h-2 overflow-hidden rounded-full bg-raised"><div className={cn("h-full rounded-full", row.shipping ? "bg-brand-500" : "bg-foreground/30")} style={{ width: `${(row.accuracy ?? 0) * 100}%` }} /></div>
                  <span className="text-right font-mono text-[11.5px] tabular-nums">{pct(row.accuracy)}</span>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Sample efficiency</h4>
              <LearningCurve curve={report.learning_curve} baseline={zeroShot} />
            </section>
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Calibration <span className="font-normal normal-case">· error {pct(report.holdout.ece, 1)}</span></h4>
              {report.holdout.reliability.length ? <ReliabilityChart bins={report.holdout.reliability} /> : <p className="m-0 text-[12px] text-muted-foreground">No held-out predictions yet.</p>}
            </section>
          </div>

          {!!report.holdout.by_difficulty?.length && (
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Accuracy by difficulty</h4>
              <DifficultyChart buckets={report.holdout.by_difficulty} />
            </section>
          )}

          {classification && (
            <section>
              <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Per-class agreement (held-out)</h4>
              <ClassificationTable classification={classification} />
            </section>
          )}

          <section>
            <h4 className="m-0 mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">What drives decisions</h4>
            <ul className="m-0 list-none space-y-1.5 p-0">
              {report.drivers.slice(0, 6).map((d) => (
                <li key={d.question} className="grid grid-cols-[1fr_5rem_2.75rem] items-center gap-2.5">
                  <span className="min-w-0 truncate text-[12px]" title={d.prompt}>{d.prompt} <span className="ml-1 rounded bg-raised px-1 font-mono text-[10px] text-muted-foreground">{KIND_LABEL[d.kind]}</span></span>
                  <div className="h-1.5 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-foreground/40" style={{ width: `${d.share * 100}%` }} /></div>
                  <span className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">{pct(d.share)}</span>
                </li>
              ))}
            </ul>
          </section>

          {!report.gate.passed && (
            <ul className="m-0 list-none space-y-0.5 p-0 text-[11.5px]">
              {report.gate.checks.filter((c) => !c.passed).map((c) => <li key={c.name} className={c.blocking ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>{c.blocking ? "Blocking" : "Note"}: {c.detail}</li>)}
            </ul>
          )}

          <div className="flex flex-wrap gap-2 border-t border-border pt-3">
            <Button size="sm" disabled={!!busy} onClick={() => void ship()}><Rocket />{busy === "ship" ? "Shipping…" : report.gate.passed ? "Ship it" : "Ship anyway"}</Button>
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => send("Harden the model against manipulation attempts.")}><ShieldCheck />Harden</Button>
            <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => send("Show me the examples it got wrong so I can check the labels.")}>Review mistakes</Button>
          </div>
        </div>
      )}
    </CardShell>
  );
}
