"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Loader2, Play, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { rmCreateAnnotation, rmGetTrace, rmImportTraces, rmListTraces, rmScoreTrace, rmUpdateAnnotation } from "@/lib/api";
import type { RmRewardModelDetail, RmScoringRun, RmTraceDetail, RmTraceSummary } from "@/lib/types";
import { errorMessage } from "./rm-text";
import { isActiveJob } from "./rm-ui";

export default function CustomModelTraceSandbox({ model }: { model: RmRewardModelDetail }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [traces, setTraces] = useState<RmTraceSummary[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const [run, setRun] = useState<RmScoringRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const ready = model.status === "succeeded";
  const supported = model.metrics?.action_scoring_version === 1 || model.metrics?.trace_scoring_version === 1;
  const active = !!run && isActiveJob(run.status);
  const disabled = busy || active;

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      setListLoading(true); setListError(null);
      void rmListTraces(25, 0, query).then((result) => {
        if (!cancelled) setTraces(result.traces.filter((item) => item.can_score !== false));
      }).catch((e) => { if (!cancelled) setListError(errorMessage(e)); })
        .finally(() => { if (!cancelled) setListLoading(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, refresh]);

  useEffect(() => {
    if (!trace || !active || !run) return;
    let cancelled = false;
    const timer = setInterval(() => {
      void rmGetTrace(trace.id).then((detail) => {
        if (cancelled) return;
        const updated = detail.scoring_runs?.find((item) => item.id === run.id);
        if (updated) {
          setRun(updated);
          if (!isActiveJob(updated.status)) setTrace(detail);
        }
        setError(null);
      }).catch((e) => { if (!cancelled) setError(`Couldn’t refresh scoring: ${errorMessage(e)}. Retrying…`); });
    }, 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [trace, active, run]);

  async function select(id: string) {
    setBusy(true); setError(null); setNotice(null); setRun(null); setTrace(null);
    try {
      const detail = await rmGetTrace(id);
      setTrace(detail);
      const pending = detail.scoring_runs?.find((item) => item.reward_model_id === model.id && isActiveJob(item.status));
      setRun(pending ?? null);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function upload(file: File) {
    setBusy(true); setError(null); setNotice(null); setRun(null); setTrace(null);
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("Choose a trace file under 10 MB.");
      const imported = await rmImportTraces("auto", await file.text());
      if (!imported.trace_ids.length) throw new Error("No traces found in this file.");
      setTrace(await rmGetTrace(imported.trace_ids[0]));
      setRefresh((value) => value + 1);
      setNotice(imported.trace_ids.length > 1 ? `Imported ${imported.trace_ids.length} traces. The first is selected; find the others below.` : "Trace uploaded and saved to Traces.");
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); if (fileInput.current) fileInput.current.value = ""; }
  }
  async function score() {
    if (!trace) return;
    setBusy(true); setError(null);
    try { setRun(await rmScoreTrace(trace.id, model.id)); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function rate(stepId: string | null, rating: 1 | -1) {
    if (!trace) return;
    setSaving(stepId ?? "trace"); setError(null);
    try {
      const existing = trace.annotations.filter((item) => item.step_id === stepId && !item.label_error && item.rating !== null).at(-1);
      if (existing) await rmUpdateAnnotation(existing.id, { rating });
      else await rmCreateAnnotation(trace.id, { ...(stepId ? { step_id: stepId } : {}), rating });
      setTrace(await rmGetTrace(trace.id));
      setNotice("Human correction saved. It takes precedence in the next training run; this model’s weights have not changed.");
    } catch (e) { setError(errorMessage(e)); }
    finally { setSaving(null); }
  }
  const overall = trace?.scores.filter((score) => score.reward_model_id === model.id).at(-1);
  const actionScores = trace?.action_scores?.filter((score) => score.reward_model_id === model.id) ?? [];
  const showResults = !active && run?.status !== "failed";
  return <div className="space-y-5 pt-5">
    <div className="rounded-lg border border-border p-4">
      <h2 className="text-sm font-medium">Try {model.name} on a trace</h2>
      <p className="mt-1 text-xs text-muted-foreground">Run this custom model on an existing trace or upload one. Review its scores and save your corrections for the next training run.</p>
      <div className="mt-4 flex flex-wrap gap-3">
        <Button disabled={disabled} onClick={() => fileInput.current?.click()}><Upload />Upload a trace</Button>
        <input ref={fileInput} aria-label="Upload sandbox trace" type="file" accept=".json,.jsonl,.ndjson,.txt" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
        <input aria-label="Search sample traces" placeholder="Search existing traces…" disabled={disabled} value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-56 flex-1 rounded-md border border-border px-3 text-sm" />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Uploads are saved to Traces. Supported formats are detected automatically.</p>
      {listError ? <p role="alert" className="mt-3 text-xs text-red-600">{listError} <button className="underline" onClick={() => setRefresh((value) => value + 1)}>Retry</button></p> : listLoading ? <p role="status" className="mt-3 text-xs">Loading traces…</p> : <div className="mt-3 flex max-h-36 flex-wrap gap-2 overflow-auto">{traces.map((item) => <Button key={item.id} size="sm" variant={trace?.id === item.id ? "secondary" : "outline"} disabled={disabled} onClick={() => void select(item.id)}>{item.title}{model.trace_ids.includes(item.id) ? " · training trace" : ""}</Button>)}{!traces.length && <p className="text-xs text-muted-foreground">No matching traces. Upload a trace to try your model.</p>}</div>}
    </div>
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
    {notice && <p role="status" className="text-xs text-muted-foreground">{notice}</p>}
    {busy && <p role="status" className="text-xs">Loading…</p>}
    {trace && <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-sm font-medium">{trace.title}</h2><p className="text-xs text-muted-foreground">Testing model: {model.name}</p></div>
        <Button disabled={disabled || !ready || !supported} onClick={() => void score()}>{active ? <Loader2 className="animate-spin" /> : <Play />}{active ? "Scoring trace…" : "Run this model"}</Button>
      </div>
      {ready && !supported && <p className="text-xs text-muted-foreground">This checkpoint does not support trace scoring. Train a new custom model from traces to enable it.</p>}
      {active && <p role="status" className="text-sm">{run.status === "queued" ? "Queued for scoring" : "Scoring"} with {model.name}…</p>}
      {run?.status === "failed" && <p role="alert" className="text-sm text-red-600">{run.error ?? "Scoring failed. Try again."}</p>}
      {showResults && <div className="rounded-md border border-border p-4">
        <p className="text-sm">{overall ? `Overall reward: ${overall.score.toFixed(3)}` : model.metrics?.trace_scoring_version === 1 ? "No overall score from this model yet." : "This model scores individual actions; an overall trace score is not available."}</p>
        <p className="mt-1 text-xs text-muted-foreground">Higher rewards indicate this model’s preference. Scores are not probabilities. Step scores below come only from {model.name}.</p>
      </div>}
      <Rating label="Overall trace" disabled={saving !== null} value={trace.annotations.filter((a) => a.step_id === null && !a.label_error && a.rating !== null).at(-1)?.rating} onRate={(rating) => void rate(null, rating)} />
      <div className="divide-y divide-border rounded-md border border-border">{trace.steps.map((step) => {
        const score = showResults ? actionScores.find((item) => item.step_id === step.id) : undefined;
        const annotation = trace.annotations.filter((a) => a.step_id === step.id && !a.label_error && a.rating !== null).at(-1);
        return <article key={step.id} className="p-4">
          <div className="mb-2 flex flex-wrap items-center gap-3 text-xs"><span className="font-medium">{step.index + 1} · {step.role}{step.tool_name ? ` → ${step.tool_name}` : ""}</span>{score && <span className="font-mono">Reward {score.score.toFixed(3)} · credit {score.credit.toFixed(3)}</span>}</div>
          <p className="whitespace-pre-wrap break-words text-sm">{step.content}</p>
          {step.tool_input && <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">{JSON.stringify(step.tool_input, null, 2)}</pre>}
          {step.role === "assistant" && <div className="mt-3"><Rating label={`Step ${step.index + 1}`} disabled={saving !== null} value={annotation?.rating} onRate={(rating) => void rate(step.id, rating)} /></div>}
        </article>;
      })}</div>
      <Link href={`/reward-models/traces/${trace.id}`} className="text-xs underline">Open full trace to add comments and inspect automatic annotations</Link>
    </section>}
  </div>;
}
function Rating({ label, disabled, value, onRate }: { label: string; disabled: boolean; value?: number | null; onRate: (rating: 1 | -1) => void }) {
  return <div className="flex items-center gap-2 text-xs"><span>{label}: your judgment</span>{([1, -1] as const).map((rating) => <Button key={rating} size="xs" variant={value === rating ? "secondary" : "outline"} disabled={disabled} aria-pressed={value === rating} onClick={() => onRate(rating)}>{rating === 1 ? "Good" : "Bad"}</Button>)}</div>;
}
