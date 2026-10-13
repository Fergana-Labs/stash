"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { inputClass } from "@/components/workbench/workbench-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { ConfirmDialog } from "@/components/intuitions/im-ui";
import ItemView from "@/components/intuitions/ItemView";
import AgentUsagePanel from "@/components/intuitions/AgentUsagePanel";
import { ProbabilityBars, RubricAnswersView } from "@/components/intuitions/ProbabilityBars";
import {
  evalAddExamples, evalAddTrace, evalPrepare, imDraftRubric, imEditDraft, imEditExample, imExamples, imFit, imGet, imGrade, imPredict, imPredictions, imPromote, imReview,
  type Example, type Item, type LoggedPrediction, type ModelDetail, type Prediction,
} from "@/lib/intuition-api";
import EvalInput from "./EvalInput";
import ModelTraceConversation from "@/components/reward-models/ModelTraceConversation";
import type { RmTraceDetail } from "@/lib/types";

export default function EvalWorkspace({ id, onUpdated, embedded = false }: { id: string; onUpdated?: () => void; embedded?: boolean }) {
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
  const [guidance, setGuidance] = useState("");
  const [exampleFeedback, setExampleFeedback] = useState<Record<string, string>>({});
  const [testItem, setTestItem] = useState<Item | null>(null);
  const [inputRevision, setInputRevision] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const load = useCallback(async () => {
    const [next, rows] = await Promise.all([imGet(id), imExamples(id)]);
    setDetail(next); setExamples(rows);
    if (initialized.current !== id) { initialized.current = id; setDescription((next.draft ?? next.active)?.description ?? ""); }
  }, [id]);
  useEffect(() => { void load().catch((e) => setError(errorMessage(e))); }, [load]);
  const version = detail?.draft ?? detail?.active;
  const labels = detail?.model.output_type === "preference" ? ["good", "bad"] : version?.labels.map((l) => l.id) ?? ["good", "bad"];
  const metrics = version?.metrics;
  const results = metrics?.eval.rows ?? [];
  async function action(message: string, perform: () => Promise<unknown>) {
    setBusy(message); setError("");
    try { await perform(); await load(); onUpdated?.(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(""); }
  }
  async function add(label: string | null) {
    if (item === null) return;
    await action("Saving example…", async () => {
      if (traceId && label) await evalAddTrace(id, traceId, label, note);
      else await evalAddExamples(id, [{ item, label, note: label === null ? "Reference material" : note }]);
      setItem(null); setTraceId(null); setNote(""); setInputRevision((value) => value + 1);
    });
  }
  async function calibrate() {
    await action("Preparing examples…", async () => {
      await imEditDraft(id, { description });
      await evalPrepare(id);
      setBusy("Drafting criteria from your examples and feedback…");
      const proposed = await imDraftRubric(id, { guidance });
      await imEditDraft(id, { rubric: proposed.rubric });
      for (let batch = 0; batch < 100; batch++) {
        setBusy("Evaluating examples…");
        const graded = await imGrade(id, 50);
        if (graded.failed) throw new Error(graded.errors.join("; ") || "Some examples could not be evaluated. Retry calibration.");
        if (!graded.remaining) {
          setBusy("Calibrating decisions and checking the held-out examples…");
          await imFit(id, { train_on: "train", calibrate: true }); return;
        }
        if (!graded.graded) throw new Error("Evaluation did not make progress. Retry calibration.");
      }
      throw new Error("More examples remain. Continue calibration.");
    });
  }
  if (!detail) return <div className="p-5">{error ? <p role="alert">{error}</p> : <p role="status" className="text-xs text-muted-foreground">Loading eval…</p>}</div>;
  return <section aria-label={`${detail.model.name} eval`} className="space-y-5 px-5 py-4">
    {!embedded && <h2 className="font-display text-lg font-semibold">{detail.model.name}</h2>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex gap-2" role="group" aria-label="Eval workspace">{["build", "test", "usage"].map((tab) => <Button key={tab} size="sm" variant={view === tab ? "secondary" : "ghost"} aria-pressed={view === tab} disabled={!!busy} onClick={() => { if (tab === view) return; setView(tab); setItem(null); setTraceId(null); if (tab === "test") setTestItem(null); }}>{tab === "build" ? "Build eval" : tab === "test" ? "Test eval" : "Usage & corrections"}</Button>)}</div>
      <span className="text-xs text-muted-foreground">{detail.active ? `Active v${detail.active.number}` : "Draft"}{detail.draft && detail.active ? ` · updating v${detail.draft.number}` : ""}</span>
    </div>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {busy && <p role="status" className="text-xs text-muted-foreground">{busy}</p>}
    {view === "build" ? <>
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">1. Describe what good looks like</h2>
          <textarea aria-label="Eval instructions" rows={5} maxLength={6000} className={inputClass} value={description} disabled={!!busy} onChange={(e) => setDescription(e.target.value)} />
          <Button size="xs" variant="outline" disabled={!!busy} onClick={() => void action("Saving instructions…", () => imEditDraft(id, { description }))}>Save instructions</Button>
          <h2 className="pt-2 text-sm font-semibold">2. Add examples and reference material</h2>
          <EvalInput key={inputRevision} onChange={setItem} onTrace={setTraceId} disabled={!!busy} />
          <textarea aria-label="Example feedback" rows={2} maxLength={2000} className={inputClass} placeholder="Why is this good or bad? What should change?" value={note} disabled={!!busy} onChange={(e) => setNote(e.target.value)} />
          <div className="flex flex-wrap gap-2">{labels.map((label) => <Button key={label} size="xs" variant="outline" disabled={!!busy || item === null} onClick={() => void add(label)}>Add {label} example</Button>)}<Button size="xs" variant="ghost" disabled={!!busy || item === null} onClick={() => void add(null)}>Add reference material</Button></div>
        </section>
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Your examples <span className="font-normal text-muted-foreground">({examples.length})</span></h2>
          <p className="text-xs text-muted-foreground">Add at least three distinct examples, including good and bad outputs. One is held aside to check the eval.</p>
          <div className="max-h-[430px] space-y-2 overflow-y-auto">{examples.map((example) => <article key={example.id} className="rounded-md border border-border p-3">
            <div className="mb-2 flex items-center justify-between gap-3"><span className="text-xs text-muted-foreground">{example.label === null ? "Reference material" : example.split === "eval" ? "Held-out check" : "Calibration example"}</span>{example.label !== null && <Select aria-label={`Label for example ${example.id}`} value={example.label} onChange={(label) => void action("Saving correction…", () => imEditExample(id, example.id, { label, needs_review: false }))} disabled={!!busy} options={labels.map((label) => ({ value: label, label }))} className="h-7 px-2 text-xs" />}</div>
            <ItemView item={example.item} />{example.label !== null && <div className="mt-2 space-y-2"><textarea aria-label={`Feedback for example ${example.id}`} maxLength={2000} rows={2} className={inputClass} disabled={!!busy} value={exampleFeedback[example.id] ?? example.note} onChange={(e) => setExampleFeedback({ ...exampleFeedback, [example.id]: e.target.value })} placeholder="Explain what makes this good or bad…" /><div className="flex gap-2"><Button size="xs" variant="ghost" disabled={!!busy || exampleFeedback[example.id] === undefined || exampleFeedback[example.id] === example.note} onClick={() => void action("Saving feedback…", () => imEditExample(id, example.id, { note: exampleFeedback[example.id] }))}>Save feedback</Button><Button size="xs" variant="ghost" disabled={!!busy} onClick={() => { setTestItem(example.item); setView("test"); }}>Test this example</Button></div></div>}
          </article>)}{!examples.length && <p className="py-8 text-xs text-muted-foreground">Your examples will appear here.</p>}</div>
        </section>
      </div>
      <section className="space-y-3 border-t border-border pt-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-sm font-semibold">3. Calibrate and check</h2><Button size="sm" disabled={!!busy || !detail.judge.configured} onClick={() => void calibrate()}>{metrics ? "Update eval" : "Calibrate eval"}</Button></div>
        <textarea aria-label="Eval improvement feedback" rows={2} maxLength={2000} className={inputClass} placeholder="Tell us what to change about the current eval…" value={guidance} disabled={!!busy} onChange={(e) => setGuidance(e.target.value)} />
        {!detail.judge.configured && <p className="text-xs text-muted-foreground">The evaluator must be connected on the server before calibration or new predictions can run.</p>}
        {metrics && !version?.head_stale && <>
          <div className="flex flex-wrap items-baseline gap-4"><span className="text-lg font-semibold">{metrics.eval.accuracy === null ? "—" : `${Math.round(metrics.eval.accuracy * 100)}%`} agreement</span><span className="text-xs text-muted-foreground">{metrics.eval.n} held-out example{metrics.eval.n === 1 ? "" : "s"} · excluded from criteria generation and calibration</span></div>
          {metrics.eval.n < 4 && <p className="text-xs text-muted-foreground">This is a small check. Add more labeled examples before relying on this eval.</p>}
          <div className="grid gap-3 md:grid-cols-2">{results.map((row) => { const example = examples.find((e) => e.id === row.example_id); return <article key={row.example_id} className="rounded-lg border border-border p-4">
            {example && <ItemView item={example.item} />}<div className="mt-3 flex flex-wrap gap-3 text-xs"><span>Your label: <strong>{row.label}</strong></span><span>Eval: <strong className={row.label === row.predicted ? "text-success" : "text-destructive"}>{row.predicted}</strong></span><span>Probability of your label: {Math.round(row.p_true * 100)}%</span></div>
          </article>; })}</div>
          {!!detail.draft && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => detail.draft?.gate?.passed ? void action("Activating eval…", () => imPromote(id)) : setConfirm(true)}>Use this eval</Button>}
        </>}
        {!!version?.rubric.length && <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">View evaluation criteria</summary><ul className="space-y-2">{version.rubric.map((q) => <li key={q.id}>{q.prompt}</li>)}</ul></details>}
      </section>
    </> : view === "test" ? <EvalTest id={id} detail={detail} initialItem={testItem} /> : <EvalUsage id={id} labels={labels} onCorrected={() => { void load(); onUpdated?.(); }} />}
    <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Use this eval with limited validation?" description={<><p>Review the held-out scorecard before using this eval.</p>{detail.draft?.gate?.checks.filter((c) => !c.passed).map((c) => <p key={c.name}>{c.detail}</p>)}<p>Activating makes this version available to API callers.</p></>} confirmLabel="Activate anyway" onConfirm={async () => { let failed = false; await action("Activating eval…", async () => { try { await imPromote(id, true); } catch (e) { failed = true; throw e; } }); return !failed; }} />
    {!embedded && <AgentUsagePanel modelId={id} outputType={detail.model.output_type} sample={item ?? "An output or agent action to evaluate"} />}
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
  const version = detail.draft?.head && !detail.draft.head_stale ? detail.draft : detail.active;
  const labels = detail.model.output_type === "choice" ? version?.labels.map((l) => l.id) ?? [] : ["good", "bad"];
  return <div className="grid gap-6 lg:grid-cols-2"><section className="space-y-3"><div className="flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">Input</h2><Button size="sm" disabled={busy || item === null || !version?.head || version.head_stale} onClick={async () => {
    if (item === null) return; setBusy(true); setError(""); setResult(null); setReviewed(false);
    try { setResult(await imPredict(id, item, version?.status === "draft" ? "draft" : "active")); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }}>{busy ? "Evaluating…" : "Run eval"}</Button></div>{initialItem && item === initialItem && <ItemView item={initialItem} />}<EvalInput disabled={busy} onDetail={setTrace} onChange={(next) => { setItem(next); setResult(null); setError(""); }} />{!version?.head && <p className="text-xs text-muted-foreground">Calibrate the eval to start testing.</p>}</section>
    <section className="space-y-3"><h2 className="text-sm font-semibold">Scorecard</h2>{error && <p role="alert" className="text-xs text-destructive">{error}</p>}{busy && <p role="status" className="text-xs">Evaluating input…</p>}{result ? <>
      <div className="flex items-baseline gap-3"><strong className="text-xl">{result.label}</strong><span className="text-xs text-muted-foreground">{Math.round(result.confidence * 100)}% confidence · v{result.version}</span></div>
      <ProbabilityBars probabilities={result.probabilities} order={labels} highlight={result.label} />
      <RubricAnswersView rubric={version?.rubric ?? []} answers={result.rubric} />
      <textarea aria-label="Score correction feedback" className={inputClass} rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="What should the eval have judged differently?" />
      <div className="flex flex-wrap gap-2">{labels.map((label) => <Button size="xs" variant="outline" key={label} disabled={busy || reviewed || !result.prediction_id} onClick={async () => {
        setBusy(true); setError(""); try { await imReview(id, result.prediction_id!, { label, note: feedback }); setReviewed(true); }
        catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
      }}>Mark {label}</Button>)}</div>{reviewed && <p role="status" className="text-xs">Correction saved as an example. Update the eval to include it.</p>}
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
    {rows.map((row) => <details key={row.id} className="rounded-md border border-border p-3"><summary className="flex cursor-pointer flex-wrap items-center gap-3 text-xs"><span>{new Date(row.created_at).toLocaleString()}</span><span>{row.caller}</span><strong>{String(row.output.error ? "Evaluation failed" : row.output.label ?? row.output.winner ?? "Comparison")}</strong><span>v{row.version}</span><span className="ml-auto text-muted-foreground">{row.status}</span></summary><div className="mt-3 space-y-3"><ItemView item={row.input.item} />{row.input.item_b && <ItemView item={row.input.item_b} />}{row.output.error ? <p className="text-xs text-destructive">{String(row.output.error)}</p> : row.kind === "predict" && <ProbabilityBars probabilities={(row.output as Prediction).probabilities} order={Object.keys((row.output as Prediction).probabilities)} highlight={(row.output as Prediction).label} />}<details className="text-xs"><summary className="cursor-pointer text-muted-foreground">View raw result</summary><pre className="max-h-48 overflow-auto rounded bg-surface p-3 text-xs">{JSON.stringify(row.output, null, 2)}</pre></details>{row.status === "unreviewed" && <>
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
