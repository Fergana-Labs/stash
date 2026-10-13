"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { ApiError } from "@/lib/api";
import {
  imGet, imImproveStatus, imLabelQueue, imPromote, imRestore, imReview, imStartImprove,
  type Example, type Gate, type ImproveJob, type ModelDetail, type QueueItem,
} from "@/lib/intuition-api";
import { examplePreview } from "./eval-ui";

const percent = (n: number | null | undefined) => n == null ? "—" : `${Math.round(n * 100)}%`;
const CHECK_NAMES: Record<string, string> = {
  pinned_examples: "Pinned examples", no_flips: "Examples that got worse", accuracy_not_lower: "Held-out accuracy",
  log_loss_within_slack: "Held-out confidence", held_out_independent: "Independent held-out data", incumbent_graded: "Comparison data",
};

/** Apply the draft through the regression gate; a 409 means the gate blocked it. */
export async function promoteChecked(id: string): Promise<Gate | null> {
  try { await imPromote(id, false); return null; }
  catch (e) {
    if (!(e instanceof ApiError) || e.status !== 409) throw e;
    const detail = await imGet(id);
    if (!detail.draft?.gate) throw e;
    return detail.draft.gate;
  }
}

/** What a blocked save would break, with an explicit override. */
export function RegressionPanel({ gate, examples, busy, action, onOverride }: { gate: Gate; examples: Example[]; busy: boolean; action: string; onOverride: () => void }) {
  const failing = gate.checks.filter((c) => c.blocking !== false && !c.passed);
  return <section aria-label="Regressions" className="space-y-3 rounded border border-destructive/40 bg-destructive/5 p-4">
    <h2 className="flex items-center gap-2 text-sm font-semibold"><AlertTriangle className="size-4 text-destructive" />Not {action === "Apply anyway" ? "applied" : "saved"}: this version is worse on examples you rely on</h2>
    <p className="text-xs text-muted-foreground">The previous version is still serving. Fix the examples or criteria and try again, or {action.toLowerCase()} if this change is intended.</p>
    <ul className="space-y-1 text-xs">{failing.map((c) => <li key={c.name} className="flex gap-2"><span className="font-medium">{CHECK_NAMES[c.name] ?? c.name}</span><span className="text-muted-foreground">{c.detail}</span></li>)}</ul>
    {!!gate.flips?.length && <ul className="divide-y divide-border rounded border border-border bg-background text-xs">{gate.flips.map((f) => {
      const example = examples.find((e) => e.id === f.example_id);
      return <li key={f.example_id} className="space-y-1 px-3 py-2"><span className="line-clamp-2">{example ? examplePreview(example.item) : f.example_id}</span>
        <span className="flex flex-wrap gap-3 text-muted-foreground"><span>Your label: <strong className="text-foreground">{f.label}</strong></span><span>Was: {f.active}</span><span>Now: <strong className="text-destructive">{f.candidate}</strong></span>{f.pinned && <span>Pinned</span>}</span></li>;
    })}</ul>}
    <div className="flex justify-end"><Button size="sm" variant="outline" disabled={busy} onClick={onOverride}>{action}</Button></div>
  </section>;
}

export function VersionsPanel({ id, detail, busy, onChanged }: { id: string; detail: ModelDetail; busy: boolean; onChanged: (next: ModelDetail) => void }) {
  const [error, setError] = useState("");
  const [working, setWorking] = useState("");
  const versions = detail.versions.filter((v) => v.status !== "draft");
  if (!versions.length) return null;
  return <section aria-label="Versions" className="space-y-2 rounded border border-border p-4">
    <h2 className="text-sm font-semibold">Versions</h2>
    <ul className="space-y-1.5 text-xs">{versions.map((v) => <li key={v.id} className="flex items-center gap-2">
      <span className="font-medium">v{v.number}</span>
      <span className="text-muted-foreground">{v.status === "active" ? "serving" : new Date(v.promoted_at ?? v.created_at).toLocaleDateString()}</span>
      <span className="tabular-nums text-muted-foreground">{v.metrics?.eval.n ? `${percent(v.metrics.eval.accuracy)} held-out` : ""}</span>
      {v.gate?.forced && <span className="rounded border border-border px-1 text-[10px] text-muted-foreground">override</span>}
      {v.status === "retired" && v.has_head && <Button size="xs" variant="ghost" className="ml-auto" disabled={busy || !!working} onClick={async () => {
        setWorking(v.id); setError("");
        try { onChanged(await imRestore(id, v.id)); } catch (e) { setError(errorMessage(e)); } finally { setWorking(""); }
      }}>{working === v.id ? "Restoring…" : "Restore"}</Button>}
    </li>)}</ul>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </section>;
}

export function ImprovePanel({ id, detail, examples, busy, onChanged }: { id: string; detail: ModelDetail; examples: Example[]; busy: boolean; onChanged: () => void }) {
  const [job, setJob] = useState<ImproveJob | null>(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [blocked, setBlocked] = useState<Gate | null>(null);
  const refresh = useCallback(async () => setJob((await imImproveStatus(id)).job), [id]);
  useEffect(() => { void refresh().catch((e) => setError(errorMessage(e))); }, [refresh]);
  const running = job?.status === "queued" || job?.status === "running";
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => { void refresh().then(() => undefined, () => undefined); }, 3000);
    return () => clearInterval(timer);
  }, [running, refresh]);
  const [finished, setFinished] = useState<string | null>(null);
  useEffect(() => { if (job?.status === "succeeded" && job.id !== finished) { setFinished(job.id); onChanged(); } }, [job, finished, onChanged]);
  const result = job?.status === "succeeded" ? job.result : null;
  const winner = result?.candidates.find((c) => c.name === result.winner);
  const pending = !!winner && !!detail.draft && JSON.stringify(detail.draft.rubric) === JSON.stringify(winner.rubric) && !!detail.draft.gate;
  async function apply(force: boolean) {
    setWorking(true); setError("");
    try {
      if (force) { await imPromote(id, true); setBlocked(null); }
      else setBlocked(await promoteChecked(id));
      onChanged();
    } catch (e) { setError(errorMessage(e)); } finally { setWorking(false); }
  }
  return <section aria-label="Improve criteria" className="space-y-3 rounded border border-border p-4">
    <div className="flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">Improve criteria</h2>
      <Button size="xs" variant="outline" disabled={busy || running || working || !detail.active} onClick={async () => {
        setError(""); setBlocked(null);
        try { setJob(await imStartImprove(id)); } catch (e) { setError(errorMessage(e)); }
      }}>{running ? <><Loader2 className="size-3 animate-spin" />Improving…</> : <><Sparkles className="size-3" />Improve</>}</Button></div>
    <p className="text-xs text-muted-foreground">Tries alternative criteria on your calibration examples and keeps the best. Held-out examples stay untouched for the check.</p>
    {!detail.active && <p className="text-xs text-muted-foreground">Save the eval first.</p>}
    {running && <p role="status" className="text-xs">{job?.progress.message ?? "Working…"}{job?.progress.total ? ` ${job.progress.completed ?? 0}/${job.progress.total}` : ""}</p>}
    {job?.status === "failed" && <p role="alert" className="text-xs text-destructive">{job.error}</p>}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {result && <div className="space-y-2">
      <table aria-label="Criteria candidates" className="w-full text-left text-[11px]"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-1 font-medium">Candidate</th><th className="pl-2 text-right font-medium">Questions</th><th className="pl-2 text-right font-medium">Accuracy</th></tr></thead>
        <tbody>{result.candidates.map((c) => <tr key={c.name} className="border-b border-border/60" title={c.rationale}><td className="py-1">{c.name === result.winner && <Check className="mr-1 inline size-3 text-success" />}{c.title}</td><td className="pl-2 text-right tabular-nums">{c.questions}</td><td className="pl-2 text-right tabular-nums">{percent(c.cv_accuracy)}</td></tr>)}</tbody></table>
      <p className="text-[11px] text-muted-foreground">Cross-validated on {result.candidates[0]?.rows ?? 0} calibration examples. The winner has the best-calibrated confidence (lowest log loss); it must beat the current criteria clearly, and ties go to fewer questions.</p>
      {!result.changed ? <p className="text-xs">The current criteria are already the best of these.</p> : <>
        {!!winner?.new_questions.length && <div className="text-xs"><span className="font-medium">New or changed questions</span><ul className="mt-1 list-disc space-y-1 pl-4">{winner.new_questions.map((q) => <li key={q}>{q}</li>)}</ul></div>}
        {pending && !blocked && <Button size="sm" disabled={busy || working} onClick={() => void apply(false)}>{working ? "Applying…" : "Apply improved criteria"}</Button>}
        {!pending && <p className="text-xs text-muted-foreground">Applied or replaced by later edits.</p>}
      </>}
    </div>}
    {blocked && <RegressionPanel gate={blocked} examples={examples} busy={working} action="Apply anyway" onOverride={() => void apply(true)} />}
  </section>;
}

export function LabelQueue({ id, labels, onLabeled }: { id: string; labels: string[]; onLabeled: () => void }) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [error, setError] = useState("");
  const [working, setWorking] = useState("");
  const load = useCallback(async () => setItems(await imLabelQueue(id)), [id]);
  useEffect(() => { void load().catch((e) => setError(errorMessage(e))); }, [load]);
  const shown = items.filter((item) => item.score > 0).slice(0, 5);
  if (!shown.length && !error) return null;
  return <section aria-label="Worth labeling" className="space-y-2 rounded border border-border p-4">
    <h3 className="text-sm font-semibold">Worth labeling</h3>
    <p className="text-xs text-muted-foreground">Calls where a label teaches the eval the most: it was unsure, the input is unlike its examples, or an outcome already disagrees.</p>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    <ul className="divide-y divide-border">{shown.map((item) => <li key={item.prediction_id} className="space-y-2 py-2.5">
      <ItemView item={item.input.item} />
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground"><span>Eval said <strong className="text-foreground">{item.predicted}</strong> ({percent(item.confidence)})</span>{item.reasons.map((r) => <span key={r} className="rounded border border-border bg-surface px-1.5">{r}</span>)}{item.ref && <span>ref {item.ref}</span>}</div>
      <div className="flex flex-wrap gap-2">{(item.kind === "compare" ? ["a", "b"] : labels).map((label) => <Button key={label} size="xs" variant="outline" disabled={!!working} onClick={async () => {
        setWorking(item.prediction_id); setError("");
        try { await imReview(id, item.prediction_id, { label }); await load(); onLabeled(); } catch (e) { setError(errorMessage(e)); } finally { setWorking(""); }
      }}>Mark {label}</Button>)}</div>
    </li>)}</ul>
  </section>;
}
