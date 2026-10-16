"use client";

import { useEffect, useState } from "react";
import {tasteGet,type TasteWorkspace} from "@/lib/taste-api";
import { imGet, type ModelDetail } from "@/lib/intuition-api";
import { wzReport, type TrainingReport } from "@/lib/wizard-api";
import { pct, userCriteria } from "./wizard-ui";

function Step({ done, label, detail }: { done: boolean; label: string; detail?: string }) {
  return (
    <li className="flex items-start gap-2">
      <span className={`mt-1 size-2 shrink-0 rounded-full ${done ? "bg-emerald-500" : "border border-border"}`} />
      <div className="min-w-0"><div className="text-[12px]">{label}</div>{detail && <div className="truncate text-[11px] text-muted-foreground">{detail}</div>}</div>
    </li>
  );
}

/** The model as it stands, beside the chat: a checklist the wizard is filling in. */
export default function ModelPanel({ modelId, version }: { modelId: string | null; version: number }) {
  const [website,setWebsite]=useState<TasteWorkspace|null>(null);
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [report, setReport] = useState<TrainingReport | null>(null);
  useEffect(() => {
    if (!modelId) return;
    void tasteGet().then(setWebsite).catch(()=>{});
    imGet(modelId).then(setDetail).catch(() => {});
    wzReport(modelId).then((r) => setReport(r.report)).catch(() => {});
  }, [modelId, version]);

  if(website?.model_id===modelId && modelId) return <aside aria-label="Model" className="hidden w-72 shrink-0 overflow-y-auto border-l border-border bg-surface/30 px-4 py-4 lg:block"><h2 className="m-0 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Your eval</h2><p className="mt-2 text-[13px] font-semibold">{website.name}</p><p className="text-xs text-muted-foreground">Learned from your corrections and rendered work.</p><ul className="m-0 mt-4 list-none space-y-2.5 p-0"><Step done label="Goal and labels"/><Step done={website.reviewed>0} label="Preferences" detail={`${website.reviewed}/${website.examples.length} reviewed`}/><Step done={!!website.grader.version} label="Grader" detail={website.grader.version?`Frozen model + linear probe · ${website.grader.version.slice(0,8)}`:"Not built yet"}/><Step done={website.grader.released} label="Validation" detail={website.grader.released?"Ready to use":"Needs attention"}/><Step done={website.trials.some(t=>t.method==='gepa'&&t.status==='scored')} label="GEPA experiment"/><Step done={website.trials.some(t=>t.method==='posttrained'&&t.status==='scored')} label="Independent weight experiment"/></ul></aside>;
  const v = detail?.draft ?? detail?.active;
  const criteria = v ? userCriteria(v.rubric) : [];
  const counts = detail?.counts;
  return (
    <aside aria-label="Model" className="hidden w-72 shrink-0 overflow-y-auto border-l border-border bg-surface/30 px-4 py-4 lg:block">
      <h2 className="m-0 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Your eval</h2>
      {!modelId || !detail || !v ? (
        <p className="mt-2 text-[12px] text-muted-foreground">Appears here once the wizard creates it.</p>
      ) : (
        <>
          <p className="m-0 mt-2 text-[13px] font-semibold">{detail.model.name}</p>
          <p className="m-0 mt-0.5 line-clamp-4 text-[11.5px] text-muted-foreground">{v.description}</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {(detail.model.output_type === "preference" ? ["good", "bad"] : v.labels.map((l) => l.id)).map((l) => <span key={l} className="rounded border border-border px-1.5 py-0.5 font-mono text-[10.5px]">{l}</span>)}
          </div>
          <ul className="m-0 mt-4 list-none space-y-2.5 p-0">
            <Step done label="Goal and labels" />
            <Step done={(counts?.labeled ?? 0) >= 6} label="Labeled examples" detail={`${counts?.labeled ?? 0} labeled${counts?.needs_review ? ` · ${counts.needs_review} waiting` : ""}`} />
            <Step done={criteria.length > 0} label="Criteria" detail={criteria.length ? `${criteria.length}: ${criteria.map((q) => q.prompt).join("; ")}` : undefined} />
            <Step done={!!report} label="Trained" detail={report ? `${pct(report.holdout.accuracy)} held-out on ${report.holdout.n}` : undefined} />
            <Step done={!!detail.active} label="Live" detail={detail.active ? `version ${detail.active.number}` : undefined} />
          </ul>
          {!detail.judge.configured && <p className="mt-4 rounded-md border border-yellow-500/30 bg-yellow-500/8 px-2 py-1.5 text-[11px]">The Jev judge isn’t configured on this server (TYPESAFE_API_KEY), so training will fail.</p>}
        </>
      )}
    </aside>
  );
}
