"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { imDropFolder, imGet, type DropFolder, type ModelDetail } from "@/lib/intuition-api";
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
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [report, setReport] = useState<TrainingReport | null>(null);
  const [folder, setFolder] = useState<DropFolder | null>(null);
  useEffect(() => {
    if (!modelId) return;
    imGet(modelId).then(setDetail).catch(() => {});
    wzReport(modelId).then((r) => setReport(r.report)).catch(() => {});
    imDropFolder(modelId).then((r) => setFolder(r.folder)).catch(() => {});
  }, [modelId, version]);

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
            <Step done={(counts?.labeled ?? 0) >= 6} label="Labeled examples" detail={`${counts?.labeled ?? 0} labeled${counts?.needs_review ? `, ${counts.needs_review} waiting` : ""}`} />
            <Step done={criteria.length > 0} label="Criteria" detail={criteria.length ? `${criteria.length}: ${criteria.map((q) => q.prompt).join("; ")}` : undefined} />
            <Step done={!!report} label="Trained" detail={report ? `${pct(report.holdout.accuracy)} held-out on ${report.holdout.n}` : undefined} />
            <Step done={!!detail.active} label="Live" detail={detail.active ? `version ${detail.active.number}` : undefined} />
          </ul>
          {folder && (
            <div className="mt-4 border-t border-border pt-3">
              <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Drop folder</div>
              <Link href={folder.url} className="mt-1 block truncate text-[12px] underline underline-offset-2">{folder.name}</Link>
              <div className="text-[11px] text-muted-foreground">{folder.imported} added</div>
            </div>
          )}
          {!detail.judge.configured && <p className="mt-4 rounded-md border border-yellow-500/30 bg-yellow-500/8 px-2 py-1.5 text-[11px]">The Jev judge isn’t configured on this server (TYPESAFE_API_KEY), so training will fail.</p>}
        </>
      )}
    </aside>
  );
}
