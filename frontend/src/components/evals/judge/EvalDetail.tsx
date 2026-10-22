"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import FileThumb from "./FileThumb";
import UploadBox from "./UploadBox";
import {
  evalBuild, evalCallFilePath, evalCalls, evalDeleteExample, evalExampleFilePath, evalExamples, evalGet, evalLabelCall, evalUploadExamples,
  type Eval, type EvalCall, type EvalExample, type EvalItem, type EvalLabel,
} from "@/lib/evals-api";

const BUILDING = ["queued", "traits", "checking"];
const STAGE_TEXT: Record<string, string> = {
  queued: "starting",
  traits: "reading examples",
  checking: "checking against examples",
};

/** A judge eval: its build, its endpoint, what it learned, agent calls and examples. */
export default function EvalDetail({ id }: { id: string }) {
  const [data, setData] = useState<Eval | null>(null);
  const [calls, setCalls] = useState<EvalCall[]>([]);
  const [examples, setExamples] = useState<EvalExample[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const building = !!data?.build && BUILDING.includes(data.build.stage);

  const load = useCallback(async () => {
    try {
      const [d, c, e] = await Promise.all([evalGet(id), evalCalls(id), evalExamples(id)]);
      setData(d); setCalls(c); setExamples(e); setError("");
    } catch (e) { setError(errorMessage(e)); }
  }, [id]);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), building ? 3000 : 10000);
    return () => clearInterval(timer);
  }, [load, building]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }
  const upload = (label: EvalLabel, files: File[]) => run(`Uploading ${files.length}…`, async () => {
    const batches = Array.from({ length: Math.ceil(files.length / 4) }, (_, i) => files.slice(i * 4, i * 4 + 4));
    await Promise.all(batches.map((batch) => evalUploadExamples(id, label, batch)));
  });

  if (!data) return <EvalPageFrame title="Eval"><p role={error ? "alert" : "status"} className="text-sm text-muted-foreground">{error || "Loading…"}</p></EvalPageFrame>;
  const stale = data.ready && examples.some((e) => new Date(e.created_at) > new Date(data.updated_at));
  return (
    <EvalPageFrame title={data.name}
      actions={<Button size="sm" disabled={building || !!busy || data.examples.good < 1} onClick={() => void run("Starting the build…", () => evalBuild(id))}>{data.ready ? "Rebuild" : "Build"}</Button>}>
      <div className="max-w-5xl space-y-4">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {busy && <p role="status" className="text-sm text-muted-foreground">{busy}</p>}
        <BuildStatus data={data} building={building} />
        {stale && !building && <p className="text-sm text-amber-600">New examples since last build</p>}
        {data.ready && <Connect data={data} />}
        {data.traits.length > 0 && <Traits data={data} />}
        <section>
          <h2 className="m-0 mb-2 text-[15px] font-semibold">Examples</h2>
          <Examples id={id} examples={examples} disabled={!!busy} onUpload={(label, f) => void upload(label, f)}
            onDelete={(exampleId) => void run("Removing…", () => evalDeleteExample(id, exampleId))} />
        </section>
        <Calls id={id} calls={calls} onLabel={(callId, label, note) => void run("Saving…", () => evalLabelCall(id, callId, label, note))} />
      </div>
    </EvalPageFrame>
  );
}

function BuildStatus({ data, building }: { data: Eval; building: boolean }) {
  const build = data.build;
  if (!build) return <p className="rounded border border-border px-4 py-3 text-sm text-muted-foreground">Not built</p>;
  if (build.stage === "failed") return <p role="alert" className="rounded border border-destructive/40 px-4 py-3 text-sm text-destructive">Build failed: {build.error || "unknown error"}</p>;
  if (building) {
    const progress = build.stage === "checking" && build.total ? ` ${build.done ?? 0}/${build.total}` : "";
    return <p role="status" className="flex items-center gap-2 rounded border border-border px-4 py-3 text-sm"><Loader2 className="size-4 animate-spin" />Building your eval API endpoint<span className="text-muted-foreground">({STAGE_TEXT[build.stage]}{progress})</span></p>;
  }
  const m = build.metrics;
  return <p className="rounded border border-border px-4 py-3 text-sm">
    <b>Ready</b>, {data.examples.good} good and {data.examples.bad} bad examples
    {m && m.agreement != null && <>, agrees with your labels {Math.round(m.agreement * 100)}%</>}
  </p>;
}

function Connect({ data }: { data: Eval }) {
  const origin = typeof window === "undefined" ? "https://api.joinstash.ai" : window.location.origin;
  const url = `${origin}${data.endpoint}`;
  const json = `curl ${url} \\
  -H "Authorization: Bearer $STASH_API_KEY" -H "Content-Type: application/json" \\
  -d '{"trace": [{"role": "user", "content": "what the agent was asked"}],
       "output": {"text": "what it produced", "images": ["<base64 PNG/JPEG, optional>"]},
       "caller": "my-agent"}'`;
  const multipart = `curl ${url} -H "Authorization: Bearer $STASH_API_KEY" \\
  -F trace='[{"role": "user", "content": "what the agent was asked"}]' \\
  -F text="what it produced" -F files=@output.png -F caller=my-agent`;
  return <section className="rounded border border-border px-4 py-3">
    <h2 className="m-0 text-[15px] font-semibold">Endpoint</h2>
    <pre className="mt-2 overflow-x-auto rounded bg-surface/60 p-3 text-[12px]">{json}</pre>
    <details className="mt-2 text-[12px]">
      <summary className="cursor-pointer text-muted-foreground">With files</summary>
      <pre className="mt-1 overflow-x-auto rounded bg-surface/60 p-3">{multipart}</pre>
    </details>
  </section>;
}

function Traits({ data }: { data: Eval }) {
  return <details className="rounded border border-border px-4 py-3">
    <summary className="cursor-pointer text-[13px] font-semibold">Traits ({data.traits.length})</summary>
    {data.build?.summary && <p className="mt-2 text-[13px] text-muted-foreground">{data.build.summary}</p>}
    <ul className="mt-2 space-y-2 text-[13px]">
      {data.traits.map((t) => <li key={t.name}><b>{t.name}</b><br /><span className="text-muted-foreground">Good: {t.good}</span><br /><span className="text-muted-foreground">Bad: {t.bad}</span></li>)}
    </ul>
  </details>;
}

function ItemPreview({ item, path }: { item: EvalItem; path: (index: number) => string }) {
  const images = item.files.map((f, i) => ({ f, i })).filter(({ f }) => f.content_type.startsWith("image/"));
  const others = item.files.filter((f) => !f.content_type.startsWith("image/"));
  const lastAsk = [...item.trace].reverse().find((s) => s.role === "user");
  return <div className="min-w-0 space-y-1 text-[12px]">
    {images.length > 0 && <div className="grid gap-1">{images.map(({ f, i }) => <FileThumb key={i} path={path(i)} alt={f.name} className="aspect-square w-full" />)}</div>}
    {others.map((f) => <div key={f.key} className="truncate text-muted-foreground">{f.name}</div>)}
    {lastAsk && <div className="line-clamp-2 text-muted-foreground">Asked: {lastAsk.content}</div>}
    {item.text && <div className="line-clamp-3 whitespace-pre-wrap">{item.text}</div>}
  </div>;
}

function Calls({ id, calls, onLabel }: { id: string; calls: EvalCall[]; onLabel: (callId: string, label: EvalLabel | null, note: string) => void }) {
  // Shown once an agent has called the eval; a new eval has nothing to show here.
  if (calls.length === 0) return null;
  return <section>
    <h2 className="m-0 mb-2 text-[15px] font-semibold">Agent calls</h2>
    <div className="divide-y divide-border rounded border border-border">{calls.map((c) => <CallRow key={c.id} id={id} call={c} onLabel={onLabel} />)}</div>
  </section>;
}

function CallRow({ id, call, onLabel }: { id: string; call: EvalCall; onLabel: (callId: string, label: EvalLabel | null, note: string) => void }) {
  const [note, setNote] = useState(call.note);
  return <div className="grid gap-4 px-4 py-3 md:grid-cols-[200px_1fr_220px]">
    <ItemPreview item={call.input} path={(i) => evalCallFilePath(id, call.id, i)} />
    <div className="min-w-0 text-[13px]">
      <div className="text-[12px] text-muted-foreground">{relativeTime(call.created_at)}, {call.caller || "unknown caller"}</div>
      <div className="mt-1 text-[22px] font-semibold tabular-nums">{call.score.toFixed(2)}</div>
      {call.explanation && <p className="mt-1">{call.explanation}</p>}
      <div className="mt-1 flex flex-wrap gap-1">{call.traits.map((t) => <span key={t.trait} title={t.why} className="rounded border border-border px-1.5 py-0.5 text-[11px]">{t.trait} <b>{t.score.toFixed(2)}</b></span>)}</div>
      {call.fixes.length > 0 && <ol className="mt-1 list-decimal space-y-1 pl-5">{call.fixes.map((f, i) => <li key={i}><span className="font-medium">{f.issue}</span> <span className="text-muted-foreground">{f.fix}</span></li>)}</ol>}
    </div>
    <div className="flex flex-col gap-2 text-[12px]">
      <div className="flex gap-2">
        {(["good", "bad"] as const).map((l) => <Button key={l} size="sm" variant={call.label === l ? "default" : "outline"} onClick={() => onLabel(call.id, call.label === l ? null : l, note)}>{l === "good" ? "Good" : "Bad"}</Button>)}
      </div>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={2000} placeholder="Note" aria-label="Note on this call" className="rounded border border-border bg-background p-2" />
    </div>
  </div>;
}

function Examples({ id, examples, disabled, onUpload, onDelete }: { id: string; examples: EvalExample[]; disabled: boolean; onUpload: (label: EvalLabel, files: File[]) => void; onDelete: (exampleId: string) => void }) {
  return <div className="space-y-4">
    {(["good", "bad"] as const).map((label) => {
      const shown = examples.filter((e) => e.label === label);
      return <div key={label}>
        <div className="mb-2 flex items-center gap-3">
          <h3 className="m-0 text-[13px] font-semibold">{label === "good" ? "Good" : "Bad"} ({shown.length})</h3>
          <UploadBox compact title="Add" disabled={disabled} onFiles={(f) => onUpload(label, f)} />
        </div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2">
          {shown.map((e) => <div key={e.id} className="rounded border border-border p-1.5">
            <ItemPreview item={e.item} path={(i) => evalExampleFilePath(id, e.id, i)} />
            {e.note && <p className="mt-1 text-[11px] text-muted-foreground">“{e.note}”</p>}
            <button type="button" className="mt-1 text-[11px] text-muted-foreground hover:text-destructive" onClick={() => onDelete(e.id)}>Remove</button>
          </div>)}
        </div>
      </div>;
    })}
  </div>;
}
