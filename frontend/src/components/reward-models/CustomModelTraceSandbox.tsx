"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { rmCreateAnnotation, rmGetTrace, rmImportTraces, rmScoreTrace, rmUpdateAnnotation } from "@/lib/api";
import type { RmRewardModelDetail, RmScoringRun, RmTraceDetail } from "@/lib/types";
import { errorMessage } from "./rm-text";
import { isActiveJob } from "./rm-ui";
import TraceSandboxInput from "./TraceSandboxInput";
import TraceModelConnect from "./TraceModelConnect";

export default function CustomModelTraceSandbox({ model, embedded = false }: { model: RmRewardModelDetail; embedded?: boolean }) {
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const [outputTrace, setOutputTrace] = useState<RmTraceDetail | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [run, setRun] = useState<RmScoringRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const ready = model.status === "succeeded";
  const supported = model.metrics?.action_scoring_version === 1 || model.metrics?.trace_scoring_version === 1;
  const active = !!run && isActiveJob(run.status);
  const disabled = busy || active || saving !== null;

  useEffect(() => {
    if (!trace || !active || !run) return;
    let cancelled = false;
    const timer = setInterval(() => {
      void rmGetTrace(trace.id).then((detail) => {
        if (cancelled) return;
        const updated = detail.scoring_runs?.find((item) => item.id === run.id);
        if (updated) {
          setRun(updated);
          if (!isActiveJob(updated.status)) { setTrace(detail); setOutputTrace(detail); }
        }
        setError(null);
      }).catch((e) => { if (!cancelled) setError("Couldn’t refresh scoring: " + errorMessage(e) + ". Retrying…"); });
    }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [trace, active, run]);

  function select(detail: RmTraceDetail | null, uploaded?: boolean) {
    setTrace(detail); setOutputTrace(null); setRun(null); setError(null);
    if (!uploaded) setNotice(null);
  }
  async function upload(file: File): Promise<RmTraceDetail> {
    const imported = await rmImportTraces("auto", await file.text());
    if (!imported.trace_ids.length) throw new Error("No traces found in this file.");
    const detail = await rmGetTrace(imported.trace_ids[0]);
    setNotice(imported.trace_ids.length > 1 ? "Imported " + imported.trace_ids.length + " traces. The first is selected." : "Trace uploaded and saved to Traces.");
    return detail;
  }
  async function score() {
    if (!trace || disabled || selecting || !ready || !supported) return;
    setBusy(true); setError(null); setNotice(null); setOutputTrace(trace); setRun(null);
    try {
      const pending = trace.scoring_runs?.find((item) => item.reward_model_id === model.id && isActiveJob(item.status));
      const next = pending ?? await rmScoreTrace(trace.id, model.id);
      setRun(next);
      if (!isActiveJob(next.status)) {
        const detail = await rmGetTrace(trace.id);
        setTrace(detail); setOutputTrace(detail);
      }
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function rate(stepId: string | null, rating: 1 | -1) {
    if (!trace) return;
    setSaving(stepId ?? "trace"); setError(null);
    try {
      const existing = trace.annotations.filter((item) => item.step_id === stepId && !item.label_error && item.rating !== null).at(-1);
      if (existing) await rmUpdateAnnotation(existing.id, { rating });
      else await rmCreateAnnotation(trace.id, { ...(stepId ? { step_id: stepId } : {}), rating });
      const detail = await rmGetTrace(trace.id);
      setTrace(detail); setOutputTrace(detail);
      setNotice("Human correction saved for the next training run.");
    } catch (e) { setError(errorMessage(e)); }
    finally { setSaving(null); }
  }
  const overall = outputTrace?.scores.filter((score) => score.reward_model_id === model.id).at(-1);
  const actionScores = outputTrace?.action_scores?.filter((score) => score.reward_model_id === model.id) ?? [];
  const showGrades = ready && supported && !busy && !active && run?.status === "succeeded";
  return <div className={embedded ? undefined : "mt-4 border-t border-border"}>
    <div className="grid border-b border-border lg:grid-cols-2 lg:divide-x lg:divide-border">
      <section className="min-w-0 space-y-3 px-5 py-3" aria-label="Model input">
        <h2 className="m-0 text-[13px] font-semibold">Input</h2>
        <TraceSandboxInput disabled={disabled} scoreableOnly selectionOnly maxBytes={10 * 1024 * 1024} onChange={() => setError(null)} onTraceChange={select} onLoadingChange={setSelecting} importTrace={upload} />
        <div className="flex items-center justify-between gap-2">
          <Button size="sm" disabled={disabled || selecting || !ready || !supported || !trace} onClick={() => void score()} title={!ready ? "Training has not finished" : !supported ? "This checkpoint does not support trace scoring" : selecting ? "Loading the selected trace" : !trace ? "Choose a trace" : undefined}>
            {active || busy ? <Loader2 className="animate-spin" /> : <Play />}{active || busy ? "Running…" : "Run"}
          </Button>
        </div>
        {notice && <p role="status" className="text-xs text-muted-foreground">{notice}</p>}
      </section>
      <section className="min-w-0 border-t border-border px-5 py-3 lg:border-t-0" aria-label="Model output">
        <h2 className="m-0 mb-4 text-[13px] font-semibold">Output</h2>
        {error && <p role="alert" className="mb-3 text-xs text-destructive">{error}</p>}
        {outputTrace ? <div className="space-y-3">
            <div className="flex items-center justify-between gap-2"><h3 className="min-w-0 truncate text-xs font-medium">{outputTrace.title}</h3><Link href={"/reward-models/traces/" + outputTrace.id} className="shrink-0 text-xs text-muted-foreground hover:text-foreground">Open trace</Link></div>
            {active && <p role="status" className="flex items-center gap-2 text-xs"><Loader2 className="h-3.5 w-3.5 animate-spin" />{run.status === "queued" ? "Queued for scoring" : "Scoring"} with {model.name}…</p>}
            {run?.status === "failed" && <p role="alert" className="text-xs text-destructive">{run.error ?? "Scoring failed. Try again."}</p>}
            {showGrades && overall && <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs">Overall reward: <span className="font-mono text-lg font-semibold">{overall.score.toFixed(3)}</span></p>
              <Rating label="Overall trace" disabled={saving !== null || selecting} value={outputTrace.annotations.filter((a) => a.step_id === null && !a.label_error && a.rating !== null).at(-1)?.rating} onRate={(rating) => void rate(null, rating)} />
            </div>}
            <div className="max-h-[540px] divide-y divide-border overflow-auto border-y border-border" aria-label="Graded conversation">
              {outputTrace.steps.map((step) => {
                const score = showGrades ? actionScores.find((item) => item.step_id === step.id) : undefined;
                const annotation = outputTrace.annotations.filter((a) => a.step_id === step.id && !a.label_error && a.rating !== null).at(-1);
                return <article key={step.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span>{step.index + 1} · {step.role}{step.tool_name ? " → " + step.tool_name : ""}</span>{score && <span className="font-mono">Reward {score.score.toFixed(3)} · credit {score.credit.toFixed(3)}</span>}</div>
                  <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed">{step.content}</p>
                  {step.tool_input && <pre className="mt-2 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{JSON.stringify(step.tool_input, null, 2)}</pre>}
                  {showGrades && step.role === "assistant" && <div className="mt-2"><Rating label={"Step " + (step.index + 1)} disabled={saving !== null || selecting} value={annotation?.rating} onRate={(rating) => void rate(step.id, rating)} /></div>}
                </article>;
              })}
            </div>
          </div> : <p className="text-xs text-muted-foreground">{!ready ? (isActiveJob(model.status) ? "Training hasn’t finished yet." : model.error ?? "Training did not finish.") : !supported ? "This checkpoint does not support trace scoring." : "Choose a trace and run this model to see its scores."}</p>}
      </section>
    </div>
    <TraceModelConnect modelId={model.id} traceId={trace?.id} />
  </div>;
}
function Rating({ label, disabled, value, onRate }: { label: string; disabled: boolean; value?: number | null; onRate: (rating: 1 | -1) => void }) {
  return <div className="flex items-center gap-2 text-xs" aria-label={label + " feedback"}>{([1, -1] as const).map((rating) => <Button key={rating} size="xs" variant={value === rating ? "secondary" : "outline"} disabled={disabled} aria-pressed={value === rating} onClick={() => onRate(rating)}>{rating === 1 ? "Good" : "Bad"}</Button>)}</div>;
}
