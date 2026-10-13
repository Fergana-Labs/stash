"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, MoreHorizontal, Plus } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { evalInputClass as inputClass, evalSurfaceClass, InlinePanel, examplePreview } from "./eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import ItemView from "@/components/intuitions/ItemView";
import { ProbabilityBars, RubricAnswersView } from "@/components/intuitions/ProbabilityBars";
import {
  evalAddExamples, evalAddTrace, evalEnableUpdates, evalUpdateStatus, evalRetryUpdate, imEditDraft, imEditExample, imExamples, imGet, imPredict, imPredictions, imReview,
  type Example, type Item, type LoggedPrediction, type ModelDetail, type Prediction, type EvalUpdateStatus,
} from "@/lib/intuition-api";
import EvalInput from "./EvalInput";
import EvalEndpoint from "./EvalEndpoint";
import BulkExamples from "./BulkExamples";
import ExampleFeedback from "./ExampleFeedback";
import EvalAdvanced from "./EvalAdvanced";
import ModelTraceConversation from "@/components/reward-models/ModelTraceConversation";
import type { RmTraceDetail } from "@/lib/types";

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
  const [testItem, setTestItem] = useState<Item | null>(null);
  const [inputRevision, setInputRevision] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [update, setUpdate] = useState<EvalUpdateStatus | null>(null);
  const [savingEdits, setSavingEdits] = useState(false);
  const [savedDescription, setSavedDescription] = useState("");
  const [instructionError, setInstructionError] = useState("");
  const instructionValue = useRef("");
  const savedInstruction = useRef("");
  const editQueue = useRef<Promise<void>>(Promise.resolve());
  const completed = useRef(-1);
  const priorStatus = useRef<EvalUpdateStatus | null>(null);
  const [selectedExample, setSelectedExample] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [next, rows] = await Promise.all([imGet(id), imExamples(id)]);
    setDetail(next); setExamples(rows);
    if (initialized.current !== id) {
      initialized.current = id;
      const value = (next.draft ?? next.active)?.description ?? "";
      instructionValue.current = value; savedInstruction.current = value;
      setDescription(value); setSavedDescription(value);
    }
  }, [id]);
  const refreshUpdate = useCallback(async () => {
    const next = await evalUpdateStatus(id);
    setUpdate(next);
    const previous = priorStatus.current;
    priorStatus.current = next;
    if (next && (completed.current !== next.completed_revision || (next.stage === "Scoring new examples" && previous?.stage !== next.stage) || (next.error && previous?.error !== next.error))) {
      completed.current = next.completed_revision;
      await load();
    }
  }, [id, load]);
  useEffect(() => {
    let stopped = false;
    void evalEnableUpdates(id).then(async (next) => { if (!stopped) { setUpdate(next); completed.current = next.completed_revision; await load(); } }).catch((e) => { if (!stopped) setError(errorMessage(e)); });
    const timer = setInterval(() => { if (!stopped) void refreshUpdate().catch((e) => setError(errorMessage(e))); }, 3000);
    return () => { stopped = true; clearInterval(timer); };
  }, [id, load, refreshUpdate]);
  const saveInstructions = useCallback((value: string) => {
    editQueue.current = editQueue.current.catch(() => {}).then(async () => {
      if (initialized.current !== id || value === savedInstruction.current) return;
      setSavingEdits(true);
      try {
        await imEditDraft(id, { description: value });
        savedInstruction.current = value; setSavedDescription(value);
        if (instructionValue.current === value) setInstructionError("");
        await load(); await refreshUpdate();
      } catch (e) { if (instructionValue.current === value) setInstructionError(errorMessage(e)); }
      finally { setSavingEdits(false); }
    });
    return editQueue.current;
  }, [id, load, refreshUpdate]);
  useEffect(() => {
    if (initialized.current !== id || description === savedDescription) return;
    const timer = setTimeout(() => { void saveInstructions(description); }, 500);
    return () => clearTimeout(timer);
  }, [id, description, savedDescription, saveInstructions]);
  const version = detail?.draft ?? detail?.active;
  const labels = detail?.model.output_type === "preference" ? ["good", "bad"] : version?.labels.map((l) => l.id) ?? ["good", "bad"];
  const tableExamples = [...examples.filter((example) => example.label === null || example.split !== "eval"), ...examples.filter((example) => example.label !== null && example.split === "eval")];
  const savedVersion = detail?.active;
  const metrics = savedVersion?.metrics;
  const results = metrics?.eval.rows ?? [];

  async function action(message: string, perform: () => Promise<unknown>, onError?: (message: string) => void) {
    setBusy(message); setError("");
    try { await perform(); await load(); await refreshUpdate(); return true; }
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
  if (!detail) return <div className="p-5">{error ? <p role="alert">{error}</p> : <p role="status" className="text-xs text-muted-foreground">Loading eval…</p>}</div>;
  return <section aria-label={`${detail.model.name} eval`} className="space-y-4 pt-2">
    <div className="flex items-center justify-between gap-4">
      <h1 className="text-lg font-semibold tracking-tight">{detail.model.name}</h1>
      <div className="flex items-center gap-2"><span role="status" aria-label="Eval update status" className="flex items-center gap-1.5 text-[11px] text-muted-foreground">{savingEdits ? "Saving changes…" : update?.state === "running" ? <><Loader2 className="size-3 animate-spin" />{update.stage ?? "Updating eval…"}</> : (update?.state === "pending" || update?.state === "queued") ? "Update scheduled" : update?.state === "needs_examples" ? "Add good and bad examples" : update?.state === "failed" ? "Update failed" : "Up to date"}</span>{update?.state === "failed" && <Button size="xs" variant="outline" onClick={() => void evalRetryUpdate(id).then(setUpdate).catch((e) => setError(errorMessage(e)))}>Retry</Button>}<DropdownMenu>
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
      <div className="flex gap-1" role="group" aria-label="Eval workspace">{["build", "implementation", "test", "usage"].map((tab) => <Button key={tab} size="sm" variant="ghost" data-eval-tab className={`h-9 rounded-none border-0 border-b-2 px-3 text-xs ${view === tab ? "border-primary text-foreground" : "border-transparent text-muted-foreground"}`} aria-pressed={view === tab} disabled={!!busy} onClick={() => { if (tab === view) return; setView(tab); setSelectedExample(null); closeAdd(); if (tab === "test") setTestItem(null); }}>{tab === "build" ? "Build eval" : tab === "implementation" ? "Implementation" : tab === "test" ? "Sandbox" : "Usage & corrections"}</Button>)}</div>
    </div>
    {view === "build" && <EvalEndpoint id={id} outputType={detail.model.output_type} />}
    {error && !addOpen && !selectedExample && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {busy && !selectedExample && <p role="status" className="text-xs text-muted-foreground">{busy}</p>}
    {update?.error && <p role="alert" className="text-xs text-destructive">{update.error}</p>}
    {view === "build" ? <>
      <div className="grid items-start gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4">      <section className="space-y-3 rounded border border-border bg-surface/40 p-4">
        <h2 className="text-sm font-semibold">Instructions</h2>
        <textarea aria-label="Eval instructions" rows={5} maxLength={6000} className={inputClass} value={description} disabled={!!busy} onChange={(e) => { instructionValue.current = e.target.value; setDescription(e.target.value); }} onBlur={() => { void saveInstructions(instructionValue.current); }} />
        {instructionError && <div className="space-y-2"><p role="alert" className="text-xs text-destructive">{instructionError}</p><Button size="xs" variant="outline" onClick={() => { void saveInstructions(description); }}>Retry changes</Button></div>}
      </section>
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
        <BulkExamples id={id} onAdded={async () => { await load(); await refreshUpdate(); }}>
        <div className="max-h-[560px] overflow-auto border-t border-border">
          <table aria-label="Examples" className="w-full min-w-[560px] table-fixed text-left text-xs"><thead className="sticky top-0 z-10 bg-surface text-muted-foreground"><tr className="h-8 border-b border-border [&>th]:px-3 [&>th]:font-medium"><th className="w-8">#</th><th>Output</th><th className="w-24">Label</th><th className="w-24">Use</th><th className="w-32">Feedback</th></tr></thead><tbody>
            {tableExamples.map((example, index) => <Fragment key={example.id}><tr className="h-12 cursor-pointer border-b border-border last:border-0 hover:bg-surface [&>td]:px-3" onClick={(event) => { if (!(event.target as HTMLElement).closest("button,[role=option],[role=listbox]")) toggleExample(example.id); }}>
              <td className="tabular-nums text-muted-foreground">{index + 1}</td>
              <td><button className="block w-full py-2 text-left" onClick={() => toggleExample(example.id)} aria-expanded={selectedExample === example.id} aria-controls={`example-${example.id}`} aria-label={`Inspect example ${index + 1}`}><span className="line-clamp-2 leading-5">{examplePreview(example.item)}</span></button></td>
              <td>{example.label === null && example.note === "Reference material" ? <span className="text-muted-foreground">—</span> : <Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label={`Label for example ${example.id}`} value={example.label ?? ""} onChange={(label) => void action("Saving correction…", () => imEditExample(id, example.id, { label: label || null, needs_review: !label }))} disabled={!!busy} options={[{ value: "", label: "Unlabeled" }, ...labels.map((label) => ({ value: label, label }))]} className="h-6 w-fit px-2 text-[11px]" />}</td>
              <td><span className="rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] text-muted-foreground">{example.label === null ? (example.note === "Reference material" ? "Reference" : "Unlabeled") : example.split === "eval" ? "Holdout" : "Calibration"}</span></td>
              <td><span className="line-clamp-2 text-[11px] leading-4 text-muted-foreground">{example.label === null ? "—" : example.note || "—"}</span></td>
            </tr>{selectedExample === example.id && <tr id={`example-${example.id}`}><td colSpan={5} className="border-b border-border p-0"><InlinePanel title={`Example ${index + 1}`} onClose={() => setSelectedExample(null)} className="rounded-none border-0">          <div className="rounded border border-border bg-surface/50 p-3"><ItemView item={example.item} clamp={false} /></div>
          {(example.label !== null || example.note !== "Reference material") && <>
            <label className="block space-y-1.5"><span className="block text-xs font-medium">Expected label</span><Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label={`Label for example ${example.id}`} value={example.label ?? ""} onChange={(label) => void action("Saving correction…", () => imEditExample(id, example.id, { label: label || null, needs_review: !label }))} disabled={!!busy} options={[{ value: "", label: "Unlabeled" }, ...labels.map((label) => ({ value: label, label }))]} className="h-7 px-2 text-xs" /></label>
            <ExampleFeedback modelId={id} exampleId={example.id} note={example.note} disabled={!!busy} onSaved={async () => { await load(); await refreshUpdate(); }} />
            <div className="flex justify-end gap-2"><Button size="sm" disabled={!!busy} onClick={() => { setTestItem(example.item); setSelectedExample(null); setView("test"); }}>Open in sandbox</Button></div>
          </>}
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          {busy && <p role="status" className="text-xs text-muted-foreground">{busy}</p>}
          </InlinePanel></td></tr>}</Fragment>)}
            {!examples.length && <tr><td colSpan={5} className="px-3 py-10 text-center text-muted-foreground">No examples yet. Add an output, file, trace, or reference material to get started.</td></tr>}
          </tbody></table>
        </div></BulkExamples>
      </section>
        {metrics && !savedVersion?.head_stale && <section aria-label="Held-out checks" className="space-y-3 rounded border border-border p-4">
          <div className="flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">Held-out checks</h2>{(metrics.eval.n <= 1 || savedVersion?.gate?.checks.some((check) => check.name === "held_out_size" && !check.passed)) && <span className="rounded border border-border bg-surface px-2 py-1 text-[11px] text-muted-foreground">Limited data</span>}</div>
          <div className="text-[16px] font-semibold">{metrics.eval.accuracy === null ? "No labels checked" : `${Math.round(metrics.eval.accuracy * metrics.eval.n)} of ${metrics.eval.n} labels matched`}</div>
          <div className="grid gap-3 md:grid-cols-2">{results.map((row) => { const example = examples.find((e) => e.id === row.example_id); return <article key={row.example_id} className="rounded border border-border p-3">
            {example && <ItemView item={example.item} />}<div className="mt-3 flex flex-wrap gap-3 text-xs"><span>Your label: <strong>{row.label}</strong></span><span>Eval: <strong className={row.label === row.predicted ? "text-success" : "text-destructive"}>{row.predicted}</strong></span><span>Probability of your label: {Math.round(row.p_true * 100)}%</span></div>
          </article>; })}</div>
        </section>}

        </div>
      </div>
    </> : view === "implementation" ? <div className="space-y-4"><section aria-label="Evaluation criteria" className="space-y-3 rounded border border-border p-4"><h2 className="text-sm font-semibold">Evaluation criteria <span className="font-normal text-muted-foreground">({version?.rubric.length ?? 0})</span></h2>{version?.rubric.length ? <ol className="space-y-4 text-xs">{version.rubric.map((question, index) => <li key={question.id} className="space-y-2 border-b border-border pb-4 last:border-0 last:pb-0"><p className="font-medium">{index + 1}. {question.prompt}</p><dl className="grid gap-1.5 pl-4">{(Array.isArray(question.criteria) ? question.criteria.map((definition, option) => [String(option), definition]) : Object.entries(question.criteria)).map(([option, definition]) => <div key={option} className="flex gap-3"><dt className="min-w-12 font-mono text-muted-foreground">{option}</dt><dd>{definition}</dd></div>)}</dl></li>)}</ol> : <p className="text-xs text-muted-foreground">Criteria appear after you label good and bad examples.</p>}</section><EvalAdvanced version={detail.active ?? detail.draft} serving={!!detail.active} /></div> : view === "test" ? <EvalTest id={id} detail={detail} initialItem={testItem} /> : <EvalUsage id={id} labels={labels} onCorrected={() => { void load(); }} />}
  </section>;
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
  }}>{busy ? "Evaluating…" : "Run eval"}</Button></div><EvalInput initialItem={initialItem} disabled={busy} onDetail={setTrace} onChange={(next) => { setItem(next); setResult(null); setError(""); }} />{!version?.head && <p className="text-xs text-muted-foreground">The eval updates automatically after you label good and bad examples.</p>}</section>
    <section className="min-w-0 space-y-3 rounded border border-border p-4"><h2 className="text-sm font-semibold">Scorecard</h2>{error && <p role="alert" className="text-xs text-destructive">{error}</p>}{busy && <p role="status" className="text-xs">Evaluating input…</p>}{result ? <>
      <div className="flex items-baseline gap-3"><strong className="text-xl">{result.label}</strong><span className="text-xs text-muted-foreground">{Math.round(result.confidence * 100)}% confidence · v{result.version}</span></div>
      <ProbabilityBars probabilities={result.probabilities} order={labels} highlight={result.label} />
      <RubricAnswersView rubric={version?.rubric ?? []} answers={result.rubric} />
      <textarea aria-label="Score correction feedback" className={inputClass} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="What should the eval have judged differently?" />
      <div className="flex flex-wrap gap-2">{labels.map((label) => <Button size="xs" variant="outline" key={label} disabled={busy || reviewed || !result.prediction_id} onClick={async () => {
        setBusy(true); setError(""); try { await imReview(id, result.prediction_id!, { label, note: feedback }); setReviewed(true); }
        catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
      }}>Mark {label}</Button>)}</div>{reviewed && <p role="status" className="text-xs">Correction added. The eval will update automatically.</p>}
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
