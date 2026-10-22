"use client";

import { useCallback, useEffect, useState } from "react";
import { Layers, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imPromote, imRefineStatus, imStartRefine, type Example, type Gate, type ModelDetail, type RefineJob, type RefinePoint } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";
import { humanize } from "@/lib/behaviors-api";
import { promoteChecked, RegressionPanel, sameRubric } from "./EvalLearning";
export { sameRubric };

const percent = (n: number | null | undefined) => n == null ? "—" : `${Math.round(n * 100)}%`;
const ACCURACY = "#f97316";

const EDIT_LABEL: Record<string, string> = {
  add_criterion: "Added criterion", tighten_wording: "Tightened wording", fix_false_positives: "Fixed false positives",
  fix_false_negatives: "Fixed false negatives", point_to_evidence: "Pointed to evidence", remove: "Removed criterion",
};
export const editLabel = (kind: string) => EDIT_LABEL[kind] ?? humanize(kind);
/** One short name for what a pass changed: its first edit, plus how many more. */
export function passLabel(p: RefinePoint): string {
  if (p.pass === 0) return "Baseline";
  if (!p.edits.length) return p.note ?? "No change";
  return `${editLabel(p.edits[0].kind)}${p.edits.length > 1 ? ` +${p.edits.length - 1} more` : ""}`;
}
/** The run ended on a plateau: it finished and its last passes were rejected. */
export const gainsExhausted = (curve: RefinePoint[], finished: boolean) => finished && curve.length > 1 && !curve.at(-1)!.accepted;

/** Cross-validated accuracy by pass: accepted passes filled, rejected ones hollow and gray; hover a point for its edit (the list below spells them out). */
export function RefineCurve({ curve, finished = false }: { curve: RefinePoint[]; finished?: boolean }) {
  if (!curve.length) return null;
  const W = 520, H = 170, L = 34, R = 50, T = 24, B = 24;
  const values = curve.map((p) => p.cv_accuracy).filter((v): v is number => v != null);
  const lo = Math.max(0, Math.min(0.5, ...values) - 0.05), hi = 1;
  const last = Math.max(1, curve.at(-1)!.pass);
  const x = (pass: number) => L + (curve.length === 1 ? (W - L - R) / 2 : (pass / last) * (W - L - R));
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  // The line follows the best-so-far rubric: what is actually kept.
  const kept = curve.filter((p) => p.accepted && p.cv_accuracy != null);
  const line = kept.map((p) => `${x(p.pass).toFixed(1)},${y(p.cv_accuracy!).toFixed(1)}`).join(" ");
  const exhausted = gainsExhausted(curve, finished);
  const end = kept.at(-1);
  return <figure className="m-0">
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[560px]" role="img" aria-label="Rubric accuracy by improvement pass">
      {[lo, (lo + hi) / 2, hi].map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={0.5} /><text x={L - 4} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground font-mono text-[8px]">{Math.round(t * 100)}%</text></g>)}
      {line && <polyline points={line} fill="none" stroke={ACCURACY} strokeWidth={1.75} />}
      {exhausted && end && <line x1={x(end.pass)} x2={x(last)} y1={y(end.cv_accuracy!)} y2={y(end.cv_accuracy!)} stroke={ACCURACY} strokeDasharray="3 3" strokeWidth={1.25} opacity={0.6} />}
      {curve.filter((p) => p.cv_accuracy != null).map((p) => <g key={p.pass}>
        <circle cx={x(p.pass)} cy={y(p.cv_accuracy!)} r={p.accepted ? 3.5 : 3} fill={p.accepted ? ACCURACY : undefined} stroke={p.accepted ? ACCURACY : "currentColor"} strokeWidth={1.25} className={p.accepted ? undefined : "fill-background text-muted-foreground/60"}>
          <title>{`${p.pass === 0 ? "Baseline" : `Pass ${p.pass}`}, ${passLabel(p)}, accuracy ${percent(p.cv_accuracy)}, ${p.pass === 0 ? "starting point" : p.accepted ? "kept" : "rejected"}`}</title>
        </circle>
      </g>)}
      {exhausted && end && <text x={x(last)} y={y(end.cv_accuracy!) - 7} textAnchor="end" className="fill-muted-foreground text-[8.5px] font-medium">Gains exhausted</text>}
      {curve.map((p) => <text key={p.pass} x={x(p.pass)} y={H - 8} textAnchor="middle" className="fill-muted-foreground font-mono text-[8px]">{p.pass === 0 ? "base" : p.pass}</text>)}
    </svg>
    <figcaption className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-3" style={{ background: ACCURACY }} />Cross-validated accuracy of the kept rubric</span>
      <span>● kept, ○ rejected</span>
    </figcaption>
  </figure>;
}

/**
 * Improve rubric: edits the saved criteria pass by pass against mistakes, production
 * feedback and contradicted claims. A changed result becomes the draft, applied through the gate.
 */
export default function RefinePanel({ id, detail, examples = [], busy = false, onChanged }: { id: string; detail: ModelDetail; examples?: Example[]; busy?: boolean; onChanged: () => void }) {
  const [job, setJob] = useState<RefineJob | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [blocked, setBlocked] = useState<Gate | null>(null);
  const [finished, setFinished] = useState<string | null>(null);
  const refresh = useCallback(async () => setJob((await imRefineStatus(id)).job), [id]);
  useEffect(() => { void refresh().catch((e) => setError(errorMessage(e))); }, [refresh]);
  const running = job?.status === "queued" || job?.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void refresh().then(() => undefined, () => undefined); }, 3000);
    return () => clearInterval(timer);
  }, [running, refresh]);
  useEffect(() => { if (job?.status === "succeeded" && job.id !== finished) { setFinished(job.id); onChanged(); } }, [job, finished, onChanged]);

  const result = job?.status === "succeeded" ? job.result : null;
  const curve = result?.curve ?? job?.progress.curve ?? [];
  const pending = !!result?.changed && !!detail.draft && sameRubric(detail.draft.rubric, result.rubric) && !!detail.draft.gate;

  async function start() {
    setError(""); setBlocked(null);
    try { setJob(await imStartRefine(id)); } catch (e) { setError(errorMessage(e)); }
  }
  async function apply(force: boolean) {
    setWorking(true); setError("");
    try {
      if (force) { await imPromote(id, true); setBlocked(null); } else setBlocked(await promoteChecked(id));
      onChanged();
    } catch (e) { setError(errorMessage(e)); } finally { setWorking(false); }
  }

  return <section aria-label="Improve rubric" className="space-y-3 rounded border border-border p-4">
    <div className="flex items-center justify-between gap-2">
      <h2 className="text-sm font-semibold">Improve rubric</h2>
      <Button size="xs" variant="outline" disabled={busy || running || working || !detail.active} onClick={() => void start()}>
        {running ? <><Loader2 className="size-3 animate-spin" />Improving…</> : <><Layers className="size-3" />Improve rubric</>}
      </Button>
    </div>
    <p className="text-xs text-muted-foreground">Edits the criteria pass by pass, aimed at the eval’s mistakes, production disagreements and contradicted claims. A pass is kept only if it lowers cross-validated log loss (more right answers, or the same answers given with better-calibrated confidence); it stops when gains run out.</p>
    {!detail.active && <p className="text-xs text-muted-foreground">Save the eval first.</p>}
    {running && <p role="status" className="text-xs">{job?.progress.message ?? "Working…"}</p>}
    {job?.status === "failed" && <p role="alert" className="text-xs text-destructive">{job.error}</p>}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}

    {curve.length > 0 && <RefineCurve curve={curve} finished={!!result} />}
    {curve.length > 0 && <ol aria-label="Refinement passes" className="m-0 list-none space-y-1.5 p-0 text-xs">
      {curve.map((p) => <li key={p.pass} className="rounded border border-border px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{p.pass === 0 ? "Baseline" : `Pass ${p.pass}`}</span>
          {p.pass > 0 && <span className={cn("rounded px-1.5 py-px text-[10.5px] font-medium", p.accepted ? "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400" : "bg-muted text-muted-foreground")}>{p.accepted ? "Kept" : "Rejected"}</span>}
          <span className="tabular-nums text-muted-foreground">accuracy {percent(p.cv_accuracy)}{p.cv_log_loss != null ? `, log loss ${p.cv_log_loss.toFixed(3)}` : ""}, {p.questions} questions</span>
        </div>
        {p.edits.length > 0 && <ul className="mt-1 list-none space-y-0.5 p-0">{p.edits.map((e, i) => <li key={i} className="flex gap-1.5"><span className="shrink-0 self-start rounded border border-border px-1 text-[10px] text-muted-foreground">{editLabel(e.kind)}</span><span className="min-w-0 text-muted-foreground">{e.rationale}</span></li>)}</ul>}
        {p.note && <p className="mt-1 text-[11px] text-muted-foreground">{p.note}</p>}
      </li>)}
    </ol>}

    {result && <div className="space-y-2 text-xs">
      <p className="text-[11px] text-muted-foreground">Signals used: {result.signals.examples} examples, {result.signals.production_disagreements} production disagreements, {result.signals.contradicted_claims} contradicted claims.</p>
      {!result.changed ? <p>Gains exhausted: no pass beat the saved criteria (v{result.base_version}), so nothing changed.</p> : <>
        <p>The draft was updated with the improved rubric{result.held_out ? `: ${percent(result.held_out.accuracy)} on ${result.held_out.n} held-out examples` : ""}{result.gate ? `, gate ${result.gate.passed ? "passes" : "blocks"}` : ""}.</p>
        {result.gate && !result.gate.passed && <ul className="list-none space-y-0.5 p-0 text-[11px]">{result.gate.checks.filter((c) => !c.passed).map((c) => <li key={c.name} className={c.blocking === false ? "text-muted-foreground" : "text-destructive"}>{c.detail}</li>)}</ul>}
        {pending && !blocked && <Button size="sm" disabled={busy || working} onClick={() => void apply(false)}>{working ? "Applying…" : "Apply improved rubric"}</Button>}
        {!pending && <p className="text-muted-foreground">Applied or replaced by later edits.</p>}
      </>}
    </div>}
    {blocked && <RegressionPanel gate={blocked} examples={examples} busy={working} action="Apply anyway" onOverride={() => void apply(true)} />}
  </section>;
}
