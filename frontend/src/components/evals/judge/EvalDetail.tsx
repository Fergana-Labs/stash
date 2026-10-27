"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { EvalPageFrame, evalSurfaceClass } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import EvalChannel, { type Send } from "./EvalChannel";
import FileThumb from "./FileThumb";
import RubricPanel from "./RubricPanel";
import UploadBox from "./UploadBox";
import {
  EVAL_BUILDING, evalBuild, evalCallFilePath, evalCalls, evalDeleteExample, evalEditExample, evalEditRubric, evalExampleFilePath, evalExamples,
  evalGet, evalLabelCall, evalMessages, evalPost, evalRubric, evalUploadExamples,
  type Eval, type EvalCall, type EvalExample, type EvalItem, type EvalLabel, type EvalMessage, type EvalRubricVersion,
} from "@/lib/evals-api";

type Tab = "channel" | "examples" | "calls";

/** A judge eval: its channel, where examples are dropped in and the agent asks about them,
 * beside its rubric, which keeps up with them. Examples and agent calls are a tab away. */
export default function EvalDetail({ id }: { id: string }) {
  const [data, setData] = useState<Eval | null>(null);
  const [messages, setMessages] = useState<EvalMessage[]>([]);
  const [reading, setReading] = useState(false);
  const [versions, setVersions] = useState<EvalRubricVersion[]>([]);
  const [calls, setCalls] = useState<EvalCall[]>([]);
  const [examples, setExamples] = useState<EvalExample[]>([]);
  const [tab, setTab] = useState<Tab>("channel");
  const [error, setError] = useState("");
  // What a send left out (files that couldn't be read): kept until the next send, not
  // cleared by polling the way load errors are.
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const rubricKey = useRef("");
  const latest = useRef(0);
  const building = !!data?.build && EVAL_BUILDING.includes(data.build.stage);

  const load = useCallback(async () => {
    // Polls overlap; only the newest one's answer is shown.
    const mine = ++latest.current;
    try {
      const [d, m] = await Promise.all([evalGet(id), evalMessages(id)]);
      if (mine !== latest.current) return;
      setData(d); setMessages(m.messages); setReading(m.busy); setError("");
      // The rubric changes with its version, and its numbers when a build finishes.
      const key = `${d.version}:${d.build?.stage ?? ""}`;
      if (key !== rubricKey.current) {
        const rubric = d.version ? await evalRubric(id) : [];
        if (mine !== latest.current) return;
        setVersions(rubric);
        rubricKey.current = key;
      }
      if (tab === "examples") setExamples(await evalExamples(id));
      if (tab === "calls") setCalls(await evalCalls(id));
    } catch (e) { if (mine === latest.current) setError(errorMessage(e)); }
  }, [id, tab]);
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), reading || building ? 2000 : 8000);
    return () => clearInterval(timer);
  }, [load, reading, building]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }
  const upload = (label: EvalLabel, files: File[]) => run(`Uploading ${files.length}`, async () => {
    const batches = Array.from({ length: Math.ceil(files.length / 4) }, (_, i) => files.slice(i * 4, i * 4 + 4));
    await Promise.all(batches.map((batch) => evalUploadExamples(id, label, batch)));
  });
  const send = async ({ text, files, threadId }: Send, onProgress: (sent: number) => void) => {
    setNotice("");
    const posted = await evalPost(id, { text, files, threadId, onProgress });
    setMessages((prev) => [...prev, posted.message]);
    if (posted.skipped.length) setNotice(`Skipped ${posted.skipped.map((s) => `${s.name} (${s.error})`).join(", ")}`);
    setReading(true);
    await load();
  };
  const label = async (exampleId: string, value: EvalLabel | null) => {
    await evalEditExample(id, exampleId, value);
    await load();
  };

  if (!data) return <EvalPageFrame title="Eval"><p role={error ? "alert" : "status"} className="text-sm text-muted-foreground">{error || "Loading"}</p></EvalPageFrame>;
  const panel = versions.length > 0 || building || data.build?.stage === "failed";
  const labeled = data.examples.good + data.examples.bad;
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "channel", label: "Channel" },
    { key: "examples", label: "Examples", count: labeled + data.unlabeled },
    ...(data.calls > 0 ? [{ key: "calls" as const, label: "Agent calls", count: data.calls }] : []),
  ];
  // Wide screens: a fixed frame where the channel and the rubric scroll on their own, so the
  // composer stays put. Narrow ones: one page that scrolls, the rubric after the channel.
  return (
    <div className={cn(evalSurfaceClass, "scroll-thin flex h-full flex-col overflow-y-auto bg-background lg:overflow-hidden")}>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 pt-4 pb-2">
        <h1 className="m-0 text-[16px] font-semibold tracking-tight">{data.name}</h1>
        <nav aria-label="Eval sections" className="flex gap-1">
          {tabs.map((t) => (
            <button key={t.key} type="button" aria-current={tab === t.key ? "page" : undefined} onClick={() => setTab(t.key)}
              className={cn("h-6 rounded px-2 text-[12px]", tab === t.key ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
              {t.label}{t.count ? <span className="ml-1 tabular-nums text-muted-foreground">{t.count}</span> : null}
            </button>
          ))}
        </nav>
      </header>
      <div className={cn("grid gap-4 px-5 pb-4 lg:min-h-0 lg:flex-1", panel && "lg:grid-cols-[minmax(0,1fr)_300px]")}>
        <div className="flex min-w-0 flex-col gap-2 lg:min-h-0">
          {(error || notice) && <p role="alert" className="text-[12px] text-destructive">{error || notice}</p>}
          {busy && <p role="status" className="text-[12px] text-muted-foreground">{busy}</p>}
          {tab === "channel" && <EvalChannel evalId={id} messages={messages} onSend={send} onLabel={label} />}
          {tab !== "channel" && <div className="scroll-thin lg:min-h-0 lg:overflow-y-auto">
            {tab === "examples" && <Examples id={id} examples={examples} disabled={!!busy} onUpload={(l, f) => void upload(l, f)}
              onDelete={(exampleId) => void run("Removing", () => evalDeleteExample(id, exampleId))} />}
            {tab === "calls" && <Calls id={id} calls={calls} onLabel={(callId, l, note) => void run("Saving", () => evalLabelCall(id, callId, l, note))} />}
          </div>}
        </div>
        {panel && <div className="scroll-thin lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          <RubricPanel data={data} versions={versions}
            onSave={async (traits, base) => { setVersions(await evalEditRubric(id, traits, base)); await load(); }}
            onRewrite={() => run("Rewriting the rubric", () => evalBuild(id, true))} />
        </div>}
      </div>
    </div>
  );
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
  return <div className="divide-y divide-border rounded border border-border">{calls.map((c) => <CallRow key={c.id} id={id} call={c} onLabel={onLabel} />)}</div>;
}

function CallRow({ id, call, onLabel }: { id: string; call: EvalCall; onLabel: (callId: string, label: EvalLabel | null, note: string) => void }) {
  const [note, setNote] = useState(call.note);
  return <div className="grid gap-4 px-4 py-3 md:grid-cols-[200px_1fr_220px]">
    <ItemPreview item={call.input} path={(i) => evalCallFilePath(id, call.id, i)} />
    <div className="min-w-0 text-[13px]">
      <div className="text-[12px] text-muted-foreground">{relativeTime(call.created_at)}, {call.caller || "unknown caller"}</div>
      <div className="mt-1 text-[15px] font-semibold tabular-nums">{call.score.toFixed(2)}</div>
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
  const unlabeled = examples.filter((e) => e.label === null);
  return <div className="space-y-4">
    {(["good", "bad"] as const).map((label) => {
      const shown = examples.filter((e) => e.label === label);
      return <div key={label}>
        <div className="mb-2 flex items-center gap-3">
          <h3 className="m-0 text-[13px] font-semibold">{label === "good" ? "Good" : "Bad"} ({shown.length})</h3>
          <UploadBox compact title="Add" disabled={disabled} onFiles={(f) => onUpload(label, f)} />
        </div>
        <ExampleGrid id={id} examples={shown} onDelete={onDelete} />
      </div>;
    })}
    {unlabeled.length > 0 && <div>
      <h3 className="m-0 mb-2 text-[13px] font-semibold">Unlabeled ({unlabeled.length})</h3>
      <ExampleGrid id={id} examples={unlabeled} onDelete={onDelete} />
    </div>}
  </div>;
}

function ExampleGrid({ id, examples, onDelete }: { id: string; examples: EvalExample[]; onDelete: (exampleId: string) => void }) {
  return <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2">
    {examples.map((e) => <div key={e.id} className="rounded border border-border p-1.5">
      <ItemPreview item={e.item} path={(i) => evalExampleFilePath(id, e.id, i)} />
      {e.note && <p className="mt-1 text-[11px] text-muted-foreground">“{e.note}”</p>}
      <div className="mt-1 flex items-center justify-between gap-1 text-[11px] text-muted-foreground">
        <button type="button" className="hover:text-destructive" onClick={() => onDelete(e.id)}>Remove</button>
        {e.split === "eval" && <span>Held out</span>}
      </div>
    </div>)}
  </div>;
}
