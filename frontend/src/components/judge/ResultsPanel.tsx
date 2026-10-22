"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import ReliabilityChart from "@/components/intuitions/ReliabilityChart";
import DifficultyChart from "@/components/intuitions/DifficultyChart";
import ClassificationTable, { classificationFromRows } from "@/components/intuitions/ClassificationTable";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imExamples, imGet, type Example, type ModelDetail } from "@/lib/intuition-api";
import { wzReport, wzTrain, type TrainingReport } from "@/lib/wizard-api";
import { cn } from "@/lib/utils";
import AgreementCard from "@/components/wizard/cards/AgreementCard";
import { LearningCurve } from "@/components/wizard/cards/ReportCard";
import { issuesOf, LabelChip, labelSpace } from "@/components/wizard/labels";
import { pct, useWizard } from "@/components/wizard/wizard-ui";

const PLAIN: Record<string, string> = {
  "Jev zero-shot": "Jev asked directly, no training",
  "Embedding probe": "Looks like your examples (embeddings)",
  "Rubric criteria": "Your criteria only",
  "Fused model": "All combined — what ships",
};

function Bar({ value, strong }: { value: number | null; strong?: boolean }) {
  return <div className="h-2 overflow-hidden rounded-full bg-raised"><div className={cn("h-full rounded-full", strong ? "bg-brand-500" : "bg-foreground/30")} style={{ width: `${(value ?? 0) * 100}%` }} /></div>;
}

/** Per label (or per issue): how often the intuition got it right on held-out examples. */
function perLabel(report: TrainingReport, kind: string, options: string[]) {
  const rows = report.holdout.rows;
  return options.map((id) => {
    const relevant = kind === "multi" ? rows : rows.filter((r) => r.label === id);
    const right = kind === "multi"
      ? relevant.filter((r) => issuesOf(r.label).includes(id) === issuesOf(r.predicted).includes(id)).length
      : relevant.filter((r) => r.predicted === id).length;
    return { id, n: relevant.length, accuracy: relevant.length ? right / relevant.length : null };
  });
}

/**
 * Results, simply: how often it agrees with you on examples it never trained on,
 * how much your labels added over the judge alone, where it is wrong, and what
 * changed against the live version. The machinery is one click down.
 */
export default function ResultsPanel() {
  const { modelId, refresh, send, version } = useWizard();
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [report, setReport] = useState<TrainingReport | null | undefined>(undefined);
  const [examples, setExamples] = useState<Example[]>([]);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [d, r, ex] = await Promise.all([imGet(modelId), wzReport(modelId), imExamples(modelId)]);
      setDetail(d); setReport(r.report); setExamples(ex);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  async function train() {
    if (!modelId) return;
    setTraining(true); setError("");
    try {
      const r = await wzTrain(modelId);
      setReport(r); refresh();
      send(`Trained: ${pct(r.holdout.accuracy)} agreement on ${r.holdout.n} held-out examples.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setTraining(false); }
  }

  if (!detail || report === undefined) return <p role="status" className="text-[12px] text-muted-foreground">{error || "Loading…"}</p>;
  const space = labelSpace(detail);
  const labeled = detail.counts.labeled;
  const trainedOn = report ? report.counts.train + report.counts.held_out : 0;
  const stale = !report || labeled !== trainedOn || !!detail.draft?.head_stale;

  const trainBar = (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-3.5 py-2.5">
      <p className="m-0 flex-1 text-[12.5px] text-muted-foreground">
        {!report ? "Not trained yet. Training fits the intuition to your confirmed labels and measures it on the held-out ones (under a minute)."
          : stale ? `Your labels or setup changed since the last training (${trainedOn} → ${labeled} labels). Train again to include them.`
            : "Up to date with your labels. Train again after adding labels, corrections, or criteria."}
      </p>
      <Button size="sm" variant={stale ? "default" : "outline"} disabled={training || labeled < 2} onClick={() => void train()}>
        {training ? <><Loader2 className="animate-spin" />Training…</> : <><RefreshCw />{report ? "Train again" : "Train"}</>}
      </Button>
    </div>
  );
  if (!report) return <div className="space-y-4">{error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}{trainBar}</div>;

  const zeroShot = report.leaderboard.find((r) => r.name === "Jev zero-shot")?.accuracy ?? null;
  const acc = report.holdout.accuracy;
  const lift = acc != null && zeroShot != null ? acc - zeroShot : null;
  const byId = new Map(examples.map((e) => [e.id, e]));
  const mistakes = report.holdout.rows.filter((r) => r.predicted !== r.label);
  const per = perLabel(report, space.kind, space.options.map((o) => o.id));
  const gate = report.gate;
  const pinned = gate.pinned && gate.pinned.n > 0 ? gate.pinned : null;
  const early = report.holdout.n < 20;
  const classification = space.kind === "multi" ? null : report.holdout.classification ?? classificationFromRows(report.holdout.rows, Object.keys(report.counts.labels));
  const trainedVersion = report.is_live ? detail.active : detail.draft ?? detail.active;
  const judgeName = trainedVersion?.provider === "agent_judge" ? "Agent Judge" : "Jev";

  return (
    <div className="flex flex-col gap-4 [&>section]:my-0">
      {error && <p role="alert" className="text-[12px] text-destructive">{error}</p>}
      {trainBar}

      <section className="grid gap-4 rounded-lg border border-border p-4 md:grid-cols-[1.1fr_1fr]">
        <div>
          <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Agrees with you</div>
          <div className="mt-1 text-4xl font-semibold tracking-tight tabular-nums">{pct(acc)}</div>
          <p className="m-0 mt-1 text-[12.5px] text-muted-foreground">
            on {report.holdout.n} examples it never trained on
            {report.holdout.accuracy_interval && <> (likely {pct(report.holdout.accuracy_interval[0])}–{pct(report.holdout.accuracy_interval[1])})</>}
            {early && <span className="ml-1 rounded bg-amber-500/12 px-1.5 py-px text-[11px] text-amber-800 dark:text-amber-300">early estimate</span>}
          </p>
          {space.kind === "multi" && <p className="m-0 mt-1 text-[11.5px] text-muted-foreground">Counts as right only when every issue matches.</p>}
          {zeroShot != null && (
            <p className="m-0 mt-3 text-[12.5px]">
              {judgeName} alone, without your labels: <b>{pct(zeroShot)}</b>
              {lift != null && <span className={cn("ml-1.5", lift > 0 ? "text-emerald-700 dark:text-emerald-400" : lift < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground")}>{lift > 0 ? `+${Math.round(lift * 100)} pts from your labels` : lift < 0 ? `${Math.round(lift * 100)} pts` : "no change yet"}</span>}
            </p>
          )}
          <ul className="m-0 mt-2 list-none space-y-0.5 p-0 text-[12.5px]">
            {pinned && <li>Must-get-right cases: <b>{Math.round((pinned.accuracy ?? 0) * pinned.n)}/{pinned.n}</b> pass</li>}
            {gate.active_version != null && <li>Vs. live v{gate.active_version}: <b className="text-emerald-700 dark:text-emerald-400">fixed {gate.fixes?.length ?? 0}</b>, <b className={(gate.flips?.length ?? 0) ? "text-red-600 dark:text-red-400" : undefined}>broke {gate.flips?.length ?? 0}</b></li>}
            <li>{gate.passed ? "Ready to ship." : `Not ready to ship: ${gate.checks.filter((c) => !c.passed && c.blocking).map((c) => c.detail).join("; ") || "see details"}`}</li>
          </ul>
        </div>
        <div>
          <div className="mb-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{space.kind === "multi" ? "Per issue" : "Per label"}</div>
          <div className="space-y-2">
            {per.map((p) => (
              <div key={p.id} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2.5 text-[12px]">
                <span className="truncate font-mono">{p.id}</span><Bar value={p.accuracy} strong />
                <span className="text-right tabular-nums text-muted-foreground">{p.n ? `${pct(p.accuracy)}, ${p.n}` : "no data"}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {report.warnings.length > 0 && report.warnings.map((w) => <p key={w} className="m-0 rounded-md border border-yellow-500/30 bg-yellow-500/8 px-2.5 py-1.5 text-[11.5px] text-yellow-900 dark:text-yellow-200">{w}</p>)}

      <section>
        <h3 className="m-0 mb-2 text-[13px] font-semibold">Where it disagrees with you <span className="font-normal text-muted-foreground">({mistakes.length} of {report.holdout.n} held out)</span></h3>
        {mistakes.length === 0 ? <p className="m-0 text-[12.5px] text-muted-foreground">No disagreements on the held-out examples.</p> : (
          <ul className="m-0 list-none space-y-2 p-0">
            {mistakes.slice(0, 8).map((m) => {
              const e = byId.get(m.example_id);
              return (
                <li key={m.example_id} className="flex items-start gap-3 rounded-lg border border-border px-3.5 py-2.5">
                  <div className="max-h-28 min-w-0 flex-1 overflow-hidden">{e ? <ItemView item={e.item} /> : <span className="text-[12px] text-muted-foreground">Example removed</span>}</div>
                  <div className="flex shrink-0 flex-col items-end gap-1 text-[11px] text-muted-foreground">
                    <span>You: <LabelChip label={m.label} kind={space.kind} tone="you" /></span>
                    <span>It: <LabelChip label={m.predicted} kind={space.kind} tone="judge" /></span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {mistakes.length > 0 && <p className="m-0 mt-1.5 text-[11.5px] text-muted-foreground">If your label is wrong, fix it in the Golden set. If it&apos;s right, add a criterion for what it missed, or more examples like it.</p>}
      </section>

      <AgreementCard />

      <details className="rounded-lg border border-border px-3.5 py-2.5 [&[open]>summary]:mb-3">
        <summary className="cursor-pointer text-[13px] font-medium">How the score is built</summary>
        <div className="space-y-5">
          <section>
            <p className="m-0 mb-2 text-[12px] text-muted-foreground">Each signal on its own, on the same held-out examples. The intuition combines them, weighted by your labels.</p>
            <div className="space-y-1.5">
              {report.leaderboard.map((row) => (
                <div key={row.name} className="grid grid-cols-[minmax(10rem,14rem)_1fr_3.5rem] items-center gap-2.5 text-[12px]" title={row.detail}>
                  <span className={cn("truncate", row.shipping && "font-semibold")}>{row.name === "Jev zero-shot" ? `${judgeName} asked directly, no training` : PLAIN[row.name] ?? row.name}</span><Bar value={row.accuracy} strong={row.shipping} />
                  <span className="text-right tabular-nums">{pct(row.accuracy)}</span>
                </div>
              ))}
            </div>
          </section>
          <div className="grid gap-5 md:grid-cols-2">
            <section><h4 className="m-0 mb-1.5 text-[12px] font-medium">More labels, more agreement</h4><LearningCurve curve={report.learning_curve} baseline={zeroShot} /></section>
            <section><h4 className="m-0 mb-1.5 text-[12px] font-medium">Is &ldquo;80% sure&rdquo; right 80% of the time?</h4>{report.holdout.reliability.length ? <ReliabilityChart bins={report.holdout.reliability} /> : <p className="m-0 text-[12px] text-muted-foreground">Not enough held-out data.</p>}</section>
          </div>
          {!!report.holdout.by_difficulty?.length && <section><h4 className="m-0 mb-1.5 text-[12px] font-medium">Accuracy by difficulty</h4><DifficultyChart buckets={report.holdout.by_difficulty} /></section>}
          {classification && <section><h4 className="m-0 mb-1.5 text-[12px] font-medium">Per-class agreement (held-out)</h4><ClassificationTable classification={classification} /></section>}
          <section>
            <h4 className="m-0 mb-1.5 text-[12px] font-medium">What moves its decisions</h4>
            <ul className="m-0 list-none space-y-1.5 p-0">
              {report.drivers.slice(0, 6).map((d) => (
                <li key={d.question} className="grid grid-cols-[1fr_5rem_2.75rem] items-center gap-2.5 text-[12px]">
                  <span className="min-w-0 truncate" title={d.prompt}>{d.kind === "verdict" ? `${judgeName}’s direct answer` : d.kind === "probe" ? "Resemblance to your examples" : d.prompt}</span>
                  <Bar value={d.share} /><span className="text-right tabular-nums text-muted-foreground">{pct(d.share)}</span>
                </li>
              ))}
            </ul>
          </section>
          <Button size="sm" variant="outline" onClick={() => send("Harden the model against manipulation attempts.")}><ShieldCheck />Test against manipulation</Button>
          <p className="m-0 text-[11px] text-muted-foreground">Trained on {report.counts.train} examples, measured on {report.counts.held_out}. Cross-validated on training labels: {pct(report.cross_validated?.accuracy)}.</p>
        </div>
      </details>
    </div>
  );
}
