"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Check, Circle, Download, Loader2, MoreHorizontal, Plus, X } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { evalInputClass as inputClass, evalSurfaceClass, InlinePanel, examplePreview } from "./eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import ItemView from "@/components/intuitions/ItemView";
import { ProbabilityBars, RubricAnswersView } from "@/components/intuitions/ProbabilityBars";
import {
  evalAddExamples, evalAddTrace, evalPrepare, imDraftRubric, imEditDraft, imEditExample, imExamples, imFit, imGet, imGrade, imPredict, imPredictions, imPromote, imReview,
  type Example, type Item, type LoggedPrediction, type ModelDetail, type Prediction,
} from "@/lib/intuition-api";
import EvalInput from "./EvalInput";
import EvalEndpoint from "./EvalEndpoint";
import ModelTraceConversation from "@/components/reward-models/ModelTraceConversation";
import type { RmTraceDetail } from "@/lib/types";

const SAVE_STEPS = ["Prepare examples", "Generate criteria", "Score examples", "Save eval"];
type SaveProgress = { status: "running" | "complete" | "failed"; step: number; message: string; startedAt: number; finishedAt?: number };

export default function EvalWorkspace({ id }: { id: string }) {
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [description, setDescription] = useState("");
  const initialized = useRef("");
  const [view, setView] = useState("build");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [item, setItem] = useState<Item | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [exampleFeedback, setExampleFeedback] = useState<Record<string, string>>({});
  const [testItem, setTestItem] = useState<Item | null>(null);
  const [inputRevision, setInputRevision] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [saveProgress, setSaveProgress] = useState<SaveProgress | null>(null);
  const [saveError, setSaveError] = useState("");
  const [selectedExample, setSelectedExample] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [next, rows] = await Promise.all([imGet(id), imExamples(id)]);
    setDetail(next); setExamples(rows);
    if (initialized.current !== id) {
      initialized.current = id;
      const value = (next.draft ?? next.active)?.description ?? "";
      setDescription(value);
    }
  }, [id]);
  useEffect(() => { void load().catch((e) => setError(errorMessage(e))); }, [load]);
  const version = detail?.draft ?? detail?.active;
  const labels = detail?.model.output_type === "preference" ? ["good", "bad"] : version?.labels.map((l) => l.id) ?? ["good", "bad"];
  const tableExamples = [...examples.filter((example) => example.label === null || example.split !== "eval"), ...examples.filter((example) => example.label !== null && example.split === "eval")];
  const savedVersion = detail?.active;
  const metrics = savedVersion?.metrics;
  const results = metrics?.eval.rows ?? [];
  const showBuildResults = saveProgress?.status !== "running" && saveProgress?.status !== "failed";
  async function action(message: string, perform: () => Promise<unknown>, onError?: (message: string) => void) {
    setBusy(message); setError("");
    try { await perform(); await load(); return true; }
    catch (e) { const message = errorMessage(e); setError(message); onError?.(message); return false; }
    finally { setBusy(""); }
  }
  function closeAdd() { setAddOpen(false); setItem(null); setTraceId(null); setNote(""); setInputRevision((value) => value + 1); }
  function toggleExample(exampleId: string) { setSelectedExample((current) => current === exampleId ? null : exampleId); }
  async function add(label: string | null) {
    if (item === null) return;
    await action("Saving example…", async () => {
      if (traceId && label) await evalAddTrace(id, traceId, label, note);
      else await evalAddExamples(id, [{ item, label, note: label === null ? "Reference material" : note }]);
      setItem(null); setTraceId(null); setNote(""); setInputRevision((value) => value + 1); setAddOpen(false);
    });
  }
  async function saveEval() {
    const startedAt = Date.now();
    setSaveError("");
    function stage(step: number, message: string) {
      setBusy(message);
      setSaveProgress({ status: "running", step, message, startedAt });
    }
    stage(0, "Saving instructions and setting aside examples for the check…");
    const succeeded = await action("Preparing examples…", async () => {
      try {
        await imEditDraft(id, { description });
        await evalPrepare(id);
        stage(1, "Creating evaluation criteria from your examples and feedback…");
        const proposed = await imDraftRubric(id, {});
        await imEditDraft(id, { rubric: proposed.rubric });
        let scored = 0;
        stage(2, "Evaluating your examples against the criteria…");
        for (let batch = 0; batch < 100; batch++) {
          const graded = await imGrade(id, 50);
          scored += graded.graded;
          if (graded.failed) throw new Error(graded.errors.join("; ") || "Some examples could not be evaluated. Try saving again.");
          if (!graded.remaining) {
            stage(3, "Learning your labels and checking the held-out examples…");
            await imFit(id, { train_on: "train", calibrate: true });
            stage(3, "Saving the updated eval…");
            // Save applies the completed evaluator in one user action. Quality
            // measurements remain visible without a separate activation workflow.
            await imPromote(id, true); return;
          }
          if (!graded.graded) throw new Error("Evaluation did not make progress. Try saving again.");
          stage(2, `${scored} evaluations scored · ${graded.remaining} remaining…`);
        }
        throw new Error("More examples remain. Try saving again.");
      } catch (e) { setSaveError(errorMessage(e)); throw e; }
    }, setSaveError);
    if (!succeeded) { try { await load(); } catch { /* Keep the build error visible if refreshing also fails. */ } }
    setSaveProgress((current) => current && ({ ...current, status: succeeded ? "complete" : "failed", step: succeeded ? SAVE_STEPS.length : current.step, message: succeeded ? "Eval saved." : "Could not save the eval. Your changes are kept; try again.", finishedAt: Date.now() }));
  }
  if (!detail) return <div className="p-5">{error ? <p role="alert">{error}</p> : <p role="status" className="text-xs text-muted-foreground">Loading eval…</p>}</div>;
  return <section aria-label={`${detail.model.name} eval`} className="space-y-4 pt-2">
    <div className="flex items-center justify-between gap-4">
      <h1 className="text-lg font-semibold tracking-tight">{detail.model.name}</h1>
      <div className="flex items-center gap-2"><Button size="sm" disabled={!!busy} onClick={() => void saveEval()}>{saveProgress?.status === "running" ? <><Loader2 className="size-3.5 animate-spin" />Saving…</> : "Save"}</Button><DropdownMenu>
        <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Eval options"><MoreHorizontal /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className={`${evalSurfaceClass} w-40 rounded-[4px] shadow-sm`}>
          <DropdownMenuItem disabled={!!busy} onSelect={() => {
            const blob = new Blob([JSON.stringify({ format: "stash-eval", format_version: 1, exported_at: new Date().toISOString(), ...detail, examples }, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `${detail.model.name.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "eval"}.json`;
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}><Download />Download</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu></div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border">
      <div className="flex gap-1" role="group" aria-label="Eval workspace">{["build", "test", "usage"].map((tab) => <Button key={tab} size="sm" variant="ghost" data-eval-tab className={`h-9 rounded-none border-0 border-b-2 px-3 text-xs ${view === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground"}`} aria-pressed={view === tab} disabled={!!busy} onClick={() => { if (tab === view) return; setView(tab); setSelectedExample(null); closeAdd(); if (tab === "test") setTestItem(null); }}>{tab === "build" ? "Build eval" : tab === "test" ? "Sandbox" : "Usage & corrections"}</Button>)}</div>
    </div>
    {view === "build" && <EvalEndpoint id={id} outputType={detail.model.output_type} />}
    {error && !addOpen && !selectedExample && !(saveProgress?.status === "failed" && error === saveError) && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {busy && !selectedExample && saveProgress?.status !== "running" && <p role="status" className="text-xs text-muted-foreground">{busy}</p>}
    {view !== "build" && saveProgress && <SaveStatus progress={saveProgress} error={saveError} onTest={() => { setTestItem(null); setView("test"); }} />}
    {view === "build" ? <>
      <div className="grid items-start gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4">      <section className="space-y-3 rounded border border-border bg-surface/40 p-4">
        <h2 className="text-sm font-semibold">Instructions</h2>
        <textarea aria-label="Eval instructions" rows={5} maxLength={6000} className={inputClass} value={description} disabled={!!busy} onChange={(e) => setDescription(e.target.value)} />
      </section>
      {saveProgress && <SaveStatus progress={saveProgress} error={saveError} onTest={() => { setTestItem(null); setView("test"); }} />}
        </aside>
        <div className="min-w-0 space-y-4">      <section aria-labelledby="eval-examples-heading" className="overflow-hidden rounded border border-border">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <h2 id="eval-examples-heading" className="text-sm font-semibold">Examples <span className="font-normal text-muted-foreground">({examples.length})</span></h2>
          <Button size="sm" variant="outline" disabled={!!busy} aria-expanded={addOpen} aria-controls="add-example-panel" onClick={() => { if (addOpen) { closeAdd(); return; } setNewLabel(labels[0] ?? ""); setError(""); setAddOpen(true); }}><Plus />Add example</Button>
        </div>
        {addOpen && <div id="add-example-panel" className="border-t border-border"><InlinePanel title="Add example" onClose={closeAdd} disabled={!!busy} className="rounded-none border-0">        <EvalInput key={inputRevision} onChange={setItem} onTrace={setTraceId} disabled={!!busy} />
        <label className="block space-y-1.5"><span className="block text-xs font-medium">How should the eval use this?</span><Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label="Example label" value={newLabel} onChange={setNewLabel} disabled={!!busy} options={[...labels.map((label) => ({ value: label, label })), { value: "", label: "Reference material" }]} className="h-8 px-3 text-xs" /></label>
        {newLabel && <textarea aria-label="Example feedback" rows={2} maxLength={2000} className={inputClass} placeholder="Why is this good or bad? What should change?" value={note} disabled={!!busy} onChange={(e) => setNote(e.target.value)} />}
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
        <div className="flex justify-end gap-2"><Button variant="ghost" size="sm" disabled={!!busy} onClick={closeAdd}>Cancel</Button><Button size="sm" disabled={!!busy || item === null} onClick={() => void add(newLabel || null)}>{busy ? "Saving…" : "Add example"}</Button></div>
        </InlinePanel></div>}
        <div className="max-h-[560px] overflow-auto border-t border-border">
          <table aria-label="Examples" className="w-full min-w-[560px] table-fixed text-left text-xs"><thead className="sticky top-0 z-10 bg-surface text-muted-foreground"><tr className="h-8 border-b border-border [&>th]:px-3 [&>th]:font-medium"><th className="w-8">#</th><th>Output</th><th className="w-24">Label</th><th className="w-24">Use</th><th className="w-32">Feedback</th></tr></thead><tbody>
            {tableExamples.map((example, index) => <Fragment key={example.id}><tr className="h-12 cursor-pointer border-b border-border last:border-0 hover:bg-surface [&>td]:px-3" onClick={(event) => { if (!(event.target as HTMLElement).closest("button,[role=option],[role=listbox]")) toggleExample(example.id); }}>
              <td className="tabular-nums text-muted-foreground">{index + 1}</td>
              <td><button className="block w-full py-2 text-left" onClick={() => toggleExample(example.id)} aria-expanded={selectedExample === example.id} aria-controls={`example-${example.id}`} aria-label={`Inspect example ${index + 1}`}><span className="line-clamp-2 leading-5">{examplePreview(example.item)}</span></button></td>
              <td>{example.label === null ? <span className="text-muted-foreground">—</span> : <Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label={`Label for example ${example.id}`} value={example.label} onChange={(label) => void action("Saving correction…", () => imEditExample(id, example.id, { label, needs_review: false }))} disabled={!!busy} options={labels.map((label) => ({ value: label, label }))} className="h-6 w-fit px-2 text-[11px]" />}</td>
              <td><span className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] text-muted-foreground">{example.label === null ? "Reference" : example.split === "eval" ? "Holdout" : "Calibration"}</span></td>
              <td><span className="line-clamp-2 text-[11px] leading-4 text-muted-foreground">{example.label === null ? "—" : example.note || "—"}</span></td>
            </tr>{selectedExample === example.id && <tr id={`example-${example.id}`}><td colSpan={5} className="border-b border-border p-0"><InlinePanel title={`Example ${index + 1}`} onClose={() => setSelectedExample(null)} className="rounded-none border-0">          <div className="rounded border border-border bg-surface/50 p-3"><ItemView item={example.item} clamp={false} /></div>
          {example.label !== null && <>
            <label className="block space-y-1.5"><span className="block text-xs font-medium">Expected label</span><Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label={`Label for example ${example.id}`} value={example.label} onChange={(label) => void action("Saving correction…", () => imEditExample(id, example.id, { label, needs_review: false }))} disabled={!!busy} options={labels.map((label) => ({ value: label, label }))} className="h-7 px-2 text-xs" /></label>
            <textarea aria-label={`Feedback for example ${example.id}`} maxLength={2000} rows={3} className={inputClass} disabled={!!busy} value={exampleFeedback[example.id] ?? example.note} onChange={(e) => setExampleFeedback({ ...exampleFeedback, [example.id]: e.target.value })} placeholder="Explain what makes this good or bad…" />
            <div className="flex justify-end gap-2"><Button size="sm" variant="outline" disabled={!!busy || exampleFeedback[example.id] === undefined || exampleFeedback[example.id] === example.note} onClick={() => void action("Saving feedback…", () => imEditExample(id, example.id, { note: exampleFeedback[example.id] }))}>Save feedback</Button><Button size="sm" disabled={!!busy} onClick={() => { setTestItem(example.item); setSelectedExample(null); setView("test"); }}>Open in sandbox</Button></div>
          </>}
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          {busy && <p role="status" className="text-xs text-muted-foreground">{busy}</p>}
          </InlinePanel></td></tr>}</Fragment>)}
            {!examples.length && <tr><td colSpan={5} className="px-3 py-10 text-center text-muted-foreground">No examples yet. Add an output, file, trace, or reference material to get started.</td></tr>}
          </tbody></table>
        </div>
      </section>
        {showBuildResults && metrics && !savedVersion?.head_stale && <section aria-label="Held-out checks" className="space-y-3 rounded border border-border p-4">
          <div className="flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">Held-out checks</h2>{(metrics.eval.n <= 1 || savedVersion?.gate?.checks.some((check) => check.name === "held_out_size" && !check.passed)) && <span className="rounded border border-border bg-surface px-2 py-1 text-[11px] text-muted-foreground">Limited data</span>}</div>
          <div className="text-[16px] font-semibold">{metrics.eval.accuracy === null ? "No labels checked" : `${Math.round(metrics.eval.accuracy * metrics.eval.n)} of ${metrics.eval.n} labels matched`}</div>
          <div className="grid gap-3 md:grid-cols-2">{results.map((row) => { const example = examples.find((e) => e.id === row.example_id); return <article key={row.example_id} className="rounded border border-border p-3">
            {example && <ItemView item={example.item} />}<div className="mt-3 flex flex-wrap gap-3 text-xs"><span>Your label: <strong>{row.label}</strong></span><span>Eval: <strong className={row.label === row.predicted ? "text-success" : "text-destructive"}>{row.predicted}</strong></span><span>Probability of your label: {Math.round(row.p_true * 100)}%</span></div>
          </article>; })}</div>
        </section>}
        {showBuildResults && !!savedVersion?.rubric.length && <section aria-label="Evaluation criteria" className="space-y-3 rounded border border-border p-4"><h2 className="text-sm font-semibold">Evaluation criteria <span className="font-normal text-muted-foreground">({savedVersion.rubric.length})</span></h2><ul className="list-disc space-y-2 pl-5 text-xs">{savedVersion.rubric.map((q) => <li key={q.id}>{q.prompt}</li>)}</ul></section>}
        </div>
      </div>
    </> : view === "test" ? <EvalTest id={id} detail={detail} initialItem={testItem} /> : <EvalUsage id={id} labels={labels} onCorrected={() => { void load(); }} />}
  </section>;
}

function SaveStatus({ progress, error, onTest }: { progress: SaveProgress; error: string; onTest: () => void }) {
  const [now, setNow] = useState(progress.startedAt);
  useEffect(() => {
    if (progress.status !== "running") return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [progress.status]);
  const elapsed = Math.max(0, Math.floor(((progress.finishedAt ?? now) - progress.startedAt) / 1000));
  return <div className="rounded border border-border bg-surface/50 p-3" aria-label="Eval save progress">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p role="status" aria-label="Save status" aria-live="polite" className="flex items-center gap-2 text-xs font-medium">{progress.status === "running" ? <Loader2 className="size-4 animate-spin" /> : progress.status === "complete" ? <Check className="size-4 text-success" /> : <X className="size-4 text-destructive" />}{progress.message}</p>
      <span className="text-xs tabular-nums text-muted-foreground">{elapsed}s {progress.status === "running" ? "elapsed" : "total"}</span>
    </div>
    <div role="progressbar" aria-label="Eval save steps completed" aria-valuemin={0} aria-valuemax={4} aria-valuenow={progress.step} aria-valuetext={`${Math.min(progress.step, 4)} of 4 steps complete`} className="my-3 h-1.5 overflow-hidden rounded-full bg-border"><div className="h-full bg-primary transition-[width]" style={{ width: `${progress.step / 4 * 100}%` }} /></div>
    <ol className="grid gap-2 text-[11px] sm:grid-cols-2">{SAVE_STEPS.map((label, step) => <li key={label} aria-current={progress.status === "running" && step === progress.step ? "step" : undefined} className={`flex items-center gap-1.5 ${step < progress.step ? "text-foreground" : "text-muted-foreground"}`}>{step < progress.step ? <Check className="size-3 text-success" /> : step === progress.step && progress.status === "running" ? <Loader2 className="size-3 animate-spin" /> : step === progress.step && progress.status === "failed" ? <X className="size-3 text-destructive" /> : <Circle className="size-3" />}{label}</li>)}</ol>
    {progress.status === "failed" && error && <p role="alert" className="mt-3 text-xs text-destructive">{error}</p>}
    {progress.status === "complete" && <Button variant="outline" size="sm" className="mt-3" onClick={onTest}>Open sandbox</Button>}
  </div>;
}

function EvalTest({ id, detail, initialItem }: { id: string; detail: ModelDetail; initialItem: Item | null }) {
  const [item, setItem] = useState<Item | null>(initialItem);
  const [result, setResult] = useState<Prediction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const version = detail.active;
  const labels = detail.model.output_type === "choice" ? version?.labels.map((l) => l.id) ?? [] : ["good", "bad"];
  return <div className="grid items-start gap-4 lg:grid-cols-2"><section className="min-w-0 space-y-3 rounded border border-border p-4"><div className="flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">Input</h2><Button size="sm" disabled={busy || item === null || !version?.head || version.head_stale} onClick={async () => {
    if (item === null) return; setBusy(true); setError(""); setResult(null); setReviewed(false);
    try { setResult(await imPredict(id, item, "active")); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }}>{busy ? "Evaluating…" : "Run eval"}</Button></div><EvalInput initialItem={initialItem} disabled={busy} onDetail={setTrace} onChange={(next) => { setItem(next); setResult(null); setError(""); }} />{!version?.head && <p className="text-xs text-muted-foreground">Save the eval to start testing.</p>}</section>
    <section className="min-w-0 space-y-3 rounded border border-border p-4"><h2 className="text-sm font-semibold">Scorecard</h2>{error && <p role="alert" className="text-xs text-destructive">{error}</p>}{busy && <p role="status" className="text-xs">Evaluating input…</p>}{result ? <>
      <div className="flex items-baseline gap-3"><strong className="text-xl">{result.label}</strong><span className="text-xs text-muted-foreground">{Math.round(result.confidence * 100)}% confidence · v{result.version}</span></div>
      <ProbabilityBars probabilities={result.probabilities} order={labels} highlight={result.label} />
      <RubricAnswersView rubric={version?.rubric ?? []} answers={result.rubric} />
      <textarea aria-label="Score correction feedback" className={inputClass} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="What should the eval have judged differently?" />
      <div className="flex flex-wrap gap-2">{labels.map((label) => <Button size="xs" variant="outline" key={label} disabled={busy || reviewed || !result.prediction_id} onClick={async () => {
        setBusy(true); setError(""); try { await imReview(id, result.prediction_id!, { label, note: feedback }); setReviewed(true); }
        catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
      }}>Mark {label}</Button>)}</div>{reviewed && <p role="status" className="text-xs">Correction added. Save the eval to include it.</p>}
    </> : !busy && <p className="text-xs text-muted-foreground">Run an eval to see its decision and criteria scores. Every result is saved in Usage & corrections.</p>}{trace && <ModelTraceConversation trace={trace} scores={[]} modelName={detail.model.name} />}</section></div>;
}

function EvalUsage({ id, labels, onCorrected }: { id: string; labels: string[]; onCorrected: () => void }) {
  const [rows, setRows] = useState<LoggedPrediction[]>([]);
  const [more, setMore] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const reload = useCallback(async () => { const data = await imPredictions(id, "all"); setRows(data); setMore(data.length === 50); }, [id]);
  useEffect(() => { void reload().catch((e) => setError(errorMessage(e))); }, [reload]);
  return <section className="space-y-3"><h2 className="text-sm font-semibold">Usage & corrections</h2><p className="text-xs text-muted-foreground">Inputs, outputs, and eval versions from the UI and API. Corrections become examples for the next update.</p>{error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {rows.map((row) => <details key={row.id} className="rounded border border-border"><summary className="flex cursor-pointer flex-wrap items-center gap-3 bg-surface/40 px-3 py-2.5 text-xs"><span>{new Date(row.created_at).toLocaleString()}</span><span>{row.caller}</span><strong>{String(row.output.error ? "Evaluation failed" : row.output.label ?? row.output.winner ?? "Comparison")}</strong><span>v{row.version}</span><span className="ml-auto text-muted-foreground">{row.status}</span></summary><div className="space-y-3 border-t border-border p-4"><ItemView item={row.input.item} />{row.input.item_b && <ItemView item={row.input.item_b} />}{row.output.error ? <p className="text-xs text-destructive">{String(row.output.error)}</p> : row.kind === "predict" && <ProbabilityBars probabilities={(row.output as Prediction).probabilities} order={Object.keys((row.output as Prediction).probabilities)} highlight={(row.output as Prediction).label} />}<details className="text-xs"><summary className="cursor-pointer text-muted-foreground">View raw result</summary><pre className="max-h-48 overflow-auto rounded bg-surface p-3 text-xs">{JSON.stringify(row.output, null, 2)}</pre></details>{row.status === "unreviewed" && <>
      <textarea aria-label={`Feedback for usage ${row.id}`} rows={2} maxLength={2000} className={inputClass} value={notes[row.id] ?? ""} onChange={(e) => setNotes({ ...notes, [row.id]: e.target.value })} placeholder="Explain your correction…" />
      <div className="flex flex-wrap gap-2">{(row.kind === "compare" ? ["a", "b"] : labels).map((label) => <Button key={label} size="xs" variant="outline" disabled={busy} onClick={async () => {
        setBusy(true); setError(""); try { await imReview(id, row.id, { label, note: notes[row.id] ?? "" }); await reload(); onCorrected(); }
        catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
      }}>Mark {label}</Button>)}</div>
    </>}</div></details>)}{!rows.length && <p className="py-6 text-xs text-muted-foreground">No eval calls recorded yet.</p>}
    {more && rows.length > 0 && <Button size="sm" variant="outline" disabled={busy} onClick={async () => {
      setBusy(true); try { const next = await imPredictions(id, "all", rows.length); setRows([...rows, ...next]); setMore(next.length === 50); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
    }}>Load more calls</Button>}
  </section>;
}
