"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Loader2, Play, Plus, X } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { rmGetPlaygroundRun, rmGetRewardModel, rmGetTrainingExamples, rmListPlaygroundRuns, rmRunPlayground } from "@/lib/api";
import type { RmPlaygroundRun, RmPlaygroundHistory, RmRewardModelDetail, RmTrainingExample } from "@/lib/types";
import { cn } from "@/lib/utils";
import { errorMessage } from "./rm-text";
import { isActiveJob } from "./rm-ui";
import ModelTiming, { trainingStage } from "./ModelTiming";

type Tab = "Playground" | "History" | "Training examples";
const field = "w-full resize-y rounded-md border border-border bg-background p-3 text-[13px] leading-relaxed outline-none placeholder:text-muted-foreground focus:border-brand-400 focus:ring-2 focus:ring-brand-400/15 disabled:opacity-60";

export default function ModelPlayground({ modelId }: { modelId: string }) {
  const [model, setModel] = useState<RmRewardModelDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useState<Tab>("Playground");
  const [prompt, setPrompt] = useState("");
  const [instructions, setInstructions] = useState("");
  const [responseA, setResponseA] = useState("");
  const [responseB, setResponseB] = useState("");
  const [compare, setCompare] = useState(false);
  const [run, setRun] = useState<RmPlaygroundRun | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollRetry, setPollRetry] = useState(0);
  const [historyVersion, setHistoryVersion] = useState(0);
  const runId = run?.id;
  const active = !!run && isActiveJob(run.status);
  const busy = submitting || active;
  const ready = model?.status === "succeeded";

  useBreadcrumbs([{ label: "Reward models", href: "/reward-models/models" }, { label: model?.name ?? "Model" }], "rm-playground");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await rmGetRewardModel(modelId);
        if (cancelled) return;
        setModel(result); setLoadError(null);
        if (isActiveJob(result.status)) timer = setTimeout(() => void load(), 3000);
      } catch (e) { if (!cancelled) setLoadError(errorMessage(e)); }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [modelId, reload]);

  // Restore an in-flight run after navigation or a refresh.
  useEffect(() => {
    let cancelled = false;
    void rmListPlaygroundRuns(modelId).then(async (history) => {
      const pending = history.items.find((item) => isActiveJob(item.status));
      if (pending) {
        const result = await rmGetPlaygroundRun(modelId, pending.id);
        if (!cancelled) { restoreInput(result); setRun(result); }
      }
    }).catch(() => { /* History has its own visible retry state. */ });
    return () => { cancelled = true; };
  }, [modelId]);

  useEffect(() => {
    if (!runId || !active) return;
    const id = runId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await rmGetPlaygroundRun(modelId, id);
        if (cancelled) return;
        setRun(result); setPollError(null);
        if (isActiveJob(result.status)) timer = setTimeout(() => void poll(), 2000);
        else setHistoryVersion((version) => version + 1);
      } catch (e) { if (!cancelled) setPollError(errorMessage(e)); }
    }
    timer = setTimeout(() => void poll(), 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [modelId, runId, active, pollRetry]); // Status changes do not restart a running poll.

  function restoreInput(result: Pick<RmPlaygroundRun, "input">) {
    setPrompt(result.input.prompt ?? ""); setInstructions(result.input.instructions ?? "");
    setResponseA(result.input.responses?.[0] ?? ""); setResponseB(result.input.responses?.[1] ?? "");
    setCompare((result.input.responses?.length ?? 0) > 1);
  }

  async function submit(exampleIndex?: number) {
    setSubmitting(true); setRunError(null); setPollError(null);
    try {
      const result = await rmRunPlayground(modelId, exampleIndex === undefined
        ? { prompt, instructions, responses: compare ? [responseA, responseB] : [responseA] }
        : { example_index: exampleIndex });
      restoreInput(result); setRun(result); setTab("Playground");
      setHistoryVersion((version) => version + 1);
    } catch (e) { setRunError(errorMessage(e)); }
    finally { setSubmitting(false); }
  }

  async function openRun(id: string) {
    setRunError(null);
    try {
      const result = await rmGetPlaygroundRun(modelId, id);
      restoreInput(result); setRun(result); setTab("Playground");
    } catch (e) { setRunError(errorMessage(e)); }
  }

  function edit() { setRun(null); setRunError(null); }
  const savedPair = run?.input.texts;

  return <div className="scroll-thin h-full overflow-y-auto px-6 py-5">
    <header className="flex items-center gap-3">
      <Link href="/reward-models/models" aria-label="Back to reward models" className="rounded p-1 text-muted-foreground hover:bg-surface hover:text-foreground"><ArrowLeft className="size-4" /></Link>
      <h1 className="m-0 truncate font-display text-[18px] font-semibold tracking-tight">{model?.name ?? "Reward model"}</h1>
      {model && <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className={cn("size-1.5 rounded-full", ready ? "bg-emerald-600/70" : "bg-muted-foreground/50")} />{trainingStage(model)}
      </span>}
      {model && <Link className="ml-auto text-xs text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground" href={`/reward-models?selected=${model.trace_ids.join(",")}`}>Trained on {model.trace_count} traces</Link>}
    </header>
    {loadError ? <ErrorNotice error={loadError} retry={() => setReload((n) => n + 1)} /> : !model ? <p role="status" className="py-8 text-sm text-muted-foreground">Loading model…</p> : <>
      <nav aria-label="Model views" className="mt-5 flex gap-6 border-b border-border">
        {(["Playground", "History", "Training examples"] as const).map((name) => <button key={name} type="button" onClick={() => { setTab(name); setRunError(null); }} aria-current={tab === name ? "page" : undefined} className={cn("-mb-px cursor-pointer border-b-2 px-0.5 pb-2.5 text-[13px]", tab === name ? "border-brand-500 font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>{name}</button>)}
      </nav>
      {!ready && <div className="border-b border-border py-3 text-sm text-muted-foreground">
        {isActiveJob(model.status) ? <>The playground will be ready when training finishes. <ModelTiming model={model} /></> : model.error ?? "Training did not finish. Create a new model to use the playground."}
      </div>}
      {runError && <ErrorNotice error={runError} />}
      {tab === "Playground" && <div className="grid gap-8 pt-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.48fr)]">
        <div className="min-w-0">
          {savedPair ? <>
            <div className="mb-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>Saved example {(run.input.example_index ?? 0) + 1} · original context</span>
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => { edit(); restoreInput({ input: {} }); }}>New input</Button>
            </div>
            {savedPair.map((text, i) => <section key={i} className="mb-4"><h2 className="mb-2 text-xs font-medium">{i === 0 ? "A · Preferred in dataset" : "B · Alternative in dataset"}</h2><ModelInput text={text} /></section>)}
            <Button size="sm" disabled={busy || !ready} onClick={() => void submit(run.input.example_index)}><Play className="size-3" />Run again</Button>
          </> : <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="space-y-4">
            <label className="block text-xs font-medium">Task / user message
              <textarea className={cn(field, "mt-2 min-h-28")} maxLength={12000} value={prompt} disabled={busy} placeholder="What is the user asking the assistant to do?" onChange={(e) => { edit(); setPrompt(e.target.value); }} />
            </label>
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">System instructions (optional)</summary>
              <textarea aria-label="System instructions" className={cn(field, "mt-2 min-h-24")} maxLength={12000} value={instructions} disabled={busy} onChange={(e) => { edit(); setInstructions(e.target.value); }} />
            </details>
            <div className={cn("grid gap-4", compare && "xl:grid-cols-2")}>
              <label className="block text-xs font-medium">{compare ? "Response A" : "Response"}
                <textarea className={cn(field, "mt-2 min-h-52")} maxLength={12000} value={responseA} disabled={busy} placeholder="Enter a response to score…" onChange={(e) => { edit(); setResponseA(e.target.value); }} />
              </label>
              {compare && <label className="block text-xs font-medium">Response B
                <textarea className={cn(field, "mt-2 min-h-52")} maxLength={12000} value={responseB} disabled={busy} placeholder="Enter an alternative response…" onChange={(e) => { edit(); setResponseB(e.target.value); }} />
              </label>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" size="sm" disabled={busy || !ready || !prompt.trim() || !responseA.trim() || (compare && !responseB.trim())}>{busy ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}{busy ? "Scoring…" : compare ? "Compare responses" : "Score response"}</Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => { edit(); setCompare(!compare); }}>{compare ? <X className="size-3" /> : <Plus className="size-3" />}{compare ? "Remove comparison" : "Compare another response"}</Button>
            </div>
          </form>}
        </div>
        <aside className="min-w-0 border-t border-border pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6" aria-label="Model result">
          <h2 className="m-0 text-xs font-medium">Result</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Higher rewards mean this model prefers the response. Scores are not probabilities.</p>
          {pollError ? <ErrorNotice error={`Couldn’t check scoring: ${pollError}`} retry={() => { setPollError(null); setPollRetry((n) => n + 1); }} />
            : active ? <div role="status" className="mt-6 flex items-start gap-2 text-sm"><Loader2 className="mt-0.5 size-4 animate-spin text-muted-foreground" /><div>{run.status === "queued" ? "Waiting to score…" : "Scoring with your model…"}<p className="mt-1 text-xs text-muted-foreground">You can leave this page. The result will appear in History.</p></div></div>
            : run?.status === "failed" ? <ErrorNotice error={run.error ?? "Scoring failed. Please try again."} />
            : run?.scores ? <Scores scores={run.scores} />
            : <p className="mt-8 text-sm leading-relaxed text-muted-foreground">Enter a task and response, or try a pair from <button type="button" className="cursor-pointer underline underline-offset-4 hover:text-foreground" onClick={() => setTab("Training examples")}>training examples</button>.</p>}
          {run?.finished_at && <p className="mt-6 text-[11px] text-muted-foreground">Scored {new Date(run.finished_at).toLocaleString()}</p>}
        </aside>
      </div>}
      {tab === "History" && <History key={historyVersion} modelId={modelId} openRun={openRun} busy={busy} />}
      {tab === "Training examples" && <Examples modelId={modelId} disabled={!ready || busy} tryPair={(index) => void submit(index)} />}
    </>}
  </div>;
}

function Scores({ scores }: { scores: number[] }) {
  const max = Math.max(...scores.map(Math.abs), 0.001);
  const difference = scores.length === 2 ? scores[0] - scores[1] : null;
  return <div className="mt-6" aria-live="polite">
    {difference !== null && <p className="mb-5 text-sm font-medium">{difference === 0 ? "Equal scores" : `Model prefers response ${difference > 0 ? "A" : "B"}`}</p>}
    {scores.map((score, i) => <div key={i} className="mb-5">
      <div className="mb-2 flex items-baseline justify-between text-xs"><span>Response {String.fromCharCode(65 + i)}</span><span className="font-mono text-lg tabular-nums">{score.toFixed(3)}</span></div>
      <div className="relative h-1.5 rounded-sm bg-surface"><span className="absolute top-0 h-full bg-brand-500/60" style={{ left: `${score < 0 ? 50 - Math.abs(score) / max * 50 : 50}%`, width: `${Math.abs(score) / max * 50}%` }} /><span className="absolute top-[-2px] left-1/2 h-2.5 w-px bg-muted-foreground/50" /></div>
    </div>)}
    {difference !== null && <p className="text-xs text-muted-foreground">Reward difference: {Math.abs(difference).toFixed(3)}</p>}
  </div>;
}

function ErrorNotice({ error, retry }: { error: string; retry?: () => void }) {
  return <div role="alert" className="my-4 text-sm text-red-600"><p className="whitespace-pre-wrap break-words">{error}</p>{retry && <Button variant="outline" size="sm" className="mt-2" onClick={retry}>Try again</Button>}</div>;
}

function Pager({ offset, total, size, change }: { offset: number; total: number; size: number; change: (offset: number) => void }) {
  return <div className="mt-4 flex items-center justify-end gap-3 text-xs text-muted-foreground"><span>{total ? `${offset + 1}–${Math.min(offset + size, total)} of ${total}` : "0 results"}</span><Button variant="ghost" size="sm" disabled={!offset} onClick={() => change(Math.max(0, offset - size))}>Previous</Button><Button variant="ghost" size="sm" disabled={offset + size >= total} onClick={() => change(offset + size)}>Next</Button></div>;
}

function History({ modelId, openRun, busy }: { modelId: string; openRun: (id: string) => Promise<void>; busy: boolean }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<RmPlaygroundHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void rmListPlaygroundRuns(modelId, offset).then((result) => { if (!cancelled) { setData(result); setError(null); } }).catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [modelId, offset, retry]);
  if (error) return <ErrorNotice error={error} retry={() => setRetry((n) => n + 1)} />;
  if (!data) return <p role="status" className="py-6 text-sm text-muted-foreground">Loading history…</p>;
  return <div className="pt-4"><table className="w-full table-fixed text-left text-xs" aria-label="Playground history">
    <thead className="border-y border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Input</th><th className="w-24">Status</th><th className="w-36">Rewards A / B</th><th className="w-44 text-right">Created</th></tr></thead>
    <tbody>{data.items.map((item) => <tr key={item.id} className="h-10 border-b border-border-subtle [&>td]:px-3"><td><button disabled={busy} onClick={() => void openRun(item.id)} className="block max-w-full cursor-pointer truncate text-left hover:underline disabled:opacity-50">{item.example_index !== null ? `Saved example ${Number(item.example_index) + 1}` : item.prompt}</button></td><td>{item.status === "succeeded" ? "Scored" : item.status === "running" ? "Scoring" : item.status === "queued" ? "Queued" : "Failed"}</td><td className="font-mono tabular-nums">{item.scores?.map((s) => s.toFixed(3)).join(" / ") ?? "—"}</td><td className="text-right text-muted-foreground"><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></td></tr>)}</tbody>
  </table>{!data.total && <p className="py-8 text-center text-sm text-muted-foreground">Your playground runs will appear here.</p>}<Pager offset={offset} total={data.total} size={20} change={(n) => { setData(null); setOffset(n); }} /></div>;
}

function Examples({ modelId, disabled, tryPair }: { modelId: string; disabled: boolean; tryPair: (index: number) => void }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: RmTrainingExample[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void rmGetTrainingExamples(modelId, offset).then((result) => { if (!cancelled) { setData(result); setError(null); } }).catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [modelId, offset, retry]);
  if (error) return <ErrorNotice error={error} retry={() => setRetry((n) => n + 1)} />;
  if (!data) return <p role="status" className="py-6 text-sm text-muted-foreground">Loading examples…</p>;
  return <div className="pt-4">
    <p className="mb-4 text-xs text-muted-foreground">Saved preference pairs from this model’s dataset. Try a pair to compare its original labels with the model’s scores.</p>
    {data.items.map((pair) => <details key={pair.index} className="border-b border-border" open={data.items.length === 1 || undefined}>
      <summary className="cursor-pointer py-3 text-[13px]">Example {pair.index + 1}<span className="ml-3 text-xs text-muted-foreground">{pair.partition === "eval" ? "Held out" : pair.partition === "train" ? "Training" : "Saved pair"}</span></summary>
      <div className="pb-4">
        <div className="mb-3 flex flex-wrap items-center gap-3"><Button size="sm" variant="outline" disabled={disabled} onClick={() => tryPair(pair.index)}><Play className="size-3" />Try this pair</Button>{pair.trace_ids.map((id, i) => <Link key={id} href={`/reward-models/traces/${id}`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">Source trace{pair.trace_ids.length > 1 ? ` ${i + 1}` : ""}<ArrowRight className="size-3" /></Link>)}</div>
        <div className="grid gap-4 xl:grid-cols-2"><section><h3 className="mb-2 text-xs font-medium">A · Preferred in dataset</h3><ModelInput text={pair.chosen} /></section><section><h3 className="mb-2 text-xs font-medium">B · Alternative in dataset</h3><ModelInput text={pair.rejected} /></section></div>
      </div>
    </details>)}
    {!data.total && <p className="py-8 text-sm text-muted-foreground">No saved preference pairs are available for this model.</p>}
    <Pager offset={offset} total={data.total} size={10} change={(n) => { setData(null); setOffset(n); }} />
  </div>;
}

function ModelInput({ text }: { text: string }) {
  let sections: Record<string, string> | null = null;
  if (text.startsWith("STASH_ACTION_V3\n")) {
    try { const value = JSON.parse(text.slice("STASH_ACTION_V3\n".length)); if (value && typeof value === "object" && Object.values(value).every((v) => typeof v === "string")) sections = value; } catch { /* Older formats stay readable as text. */ }
  }
  return <div className="scroll-thin max-h-96 overflow-auto rounded-md border border-border bg-surface/40 p-3 text-xs leading-relaxed">
    {sections ? Object.entries(sections).filter(([, value]) => value).map(([key, value]) => <div key={key} className="mb-3 last:mb-0"><div className="mb-1 font-medium capitalize text-muted-foreground">{key === "action" ? "Response / action" : key}</div><p className="whitespace-pre-wrap break-words">{value}</p></div>) : <p className="whitespace-pre-wrap break-words">{text}</p>}
  </div>;
}
