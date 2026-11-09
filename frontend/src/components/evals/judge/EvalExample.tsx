"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import FileThumb from "./FileThumb";
import { evalExample, evalExampleFilePath, evalGet, type EvalExampleDetail } from "@/lib/evals-api";

const LABELS = { good: "Good", bad: "Bad" } as const;

/** One example of a judge eval: what it is, and who added it, when, and from which session. */
export default function EvalExample({ evalId, exampleId }: { evalId: string; exampleId: string }) {
  const [example, setExample] = useState<EvalExampleDetail | null>(null);
  const [evalName, setEvalName] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    Promise.all([evalExample(evalId, exampleId), evalGet(evalId)])
      .then(([e, ev]) => { if (live) { setExample(e); setEvalName(ev.name); } })
      .catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [evalId, exampleId]);

  const back = <Link href={`/reward-models/evals/${evalId}?tab=examples`} className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground">
    <ArrowLeft className="size-3.5" aria-hidden />{evalName || "Examples"}
  </Link>;
  if (!example) return <EvalPageFrame>{back}<p role={error ? "alert" : "status"} className="mt-4 text-sm text-muted-foreground">{error || "Loading"}</p></EvalPageFrame>;

  const { item } = example;
  const images = item.files.map((f, i) => ({ f, i })).filter(({ f }) => f.content_type.startsWith("image/"));
  const others = item.files.filter((f) => !f.content_type.startsWith("image/"));
  const title = item.name || item.files[0]?.name || "Example";
  return <EvalPageFrame>
    {back}
    <h1 className="mt-2 mb-4 truncate text-[16px] font-semibold tracking-tight">{title}</h1>
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0 space-y-3 text-[13px]">
        {images.map(({ f, i }) => <FileThumb key={i} path={evalExampleFilePath(evalId, example.id, i)} alt={f.name} className="max-h-[70vh] w-full" />)}
        {others.map((f) => <div key={f.key} className="text-muted-foreground">{f.name}</div>)}
        {item.trace.length > 0 && <div className="divide-y divide-border rounded border border-border">
          {item.trace.map((t, i) => <div key={i} className="px-3 py-2">
            <div className="text-[11px] text-muted-foreground">{t.tool_name || t.role}</div>
            <div className="whitespace-pre-wrap">{t.content}</div>
          </div>)}
        </div>}
        {item.text && <div className="whitespace-pre-wrap">{item.text}</div>}
      </div>
      <dl className="grid grid-cols-[88px_minmax(0,1fr)] content-start gap-x-3 gap-y-2 text-[12px]">
        <Row label="Label">{example.label ? LABELS[example.label] : "Unlabeled"}{example.split === "eval" ? ", held out" : ""}</Row>
        <Row label="Added by">{example.added_by_name || "Unknown"}</Row>
        {example.caller && <Row label="Agent">{example.caller}</Row>}
        {example.added_via && <Row label="Through">{example.added_via === "api" ? "API" : "App"}</Row>}
        <Row label="Added"><time dateTime={example.created_at} title={new Date(example.created_at).toLocaleString()}>{relativeTime(example.created_at)}</time></Row>
        {example.session
          ? <Row label="Session"><Link href={`/sessions/${encodeURIComponent(example.session.session_id)}`} className="block truncate underline-offset-2 hover:underline">{example.session.title || example.session.session_id}</Link></Row>
          : example.session_id && <Row label="Session"><span className="block truncate font-mono text-[11px] text-muted-foreground" title={example.session_id}>{example.session_id}</span></Row>}
        {example.call && <Row label="From call">{relativeTime(example.call.created_at)}</Row>}
        {example.note && <Row label="Note">{example.note}</Row>}
      </dl>
    </div>
  </EvalPageFrame>;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <><dt className="text-muted-foreground">{label}</dt><dd className="m-0 min-w-0">{children}</dd></>;
}
