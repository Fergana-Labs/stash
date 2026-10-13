"use client";

import { useCallback, useState } from "react";
import { rmGetGepaRun } from "@/lib/api";
import type { GepaSummary } from "@/lib/monitoring-api";
import { ErrorNotice, RecordBadge, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import ContentDiff from "@/components/workbench/ContentDiff";
import { date, value } from "./RollingRewardChart";

function GepaTrial({ id }: { id: string }) {
  const loader = useCallback(() => rmGetGepaRun(id), [id]);
  const { data, error, reload } = useWorkbenchLoad(loader, 10000);
  return <div className="space-y-3 py-3 pl-6"><ErrorNotice error={error} onRetry={() => void reload()} />{!data ? <p className="text-xs text-muted-foreground">Loading candidates…</p> : <>
    <p className="text-xs text-muted-foreground">GEPA’s evaluation score is on a 0–1 scale. This run stores skill candidates; agent delivery and acceptance are not recorded here.</p>
    {data.error && <p className="text-xs text-red-600">{data.error}</p>}
    {data.candidates?.map((candidate, i) => <details key={i} className="border-b border-border-subtle pb-2 text-xs"><summary className="flex cursor-pointer gap-3"><span>{i === 0 ? "Seed skill" : `Candidate ${i}`}</span><span className="tabular-nums">{value(candidate.score)}</span><span className="text-muted-foreground">{candidate.skill === data.best_skill ? "Selected by GEPA" : i === 0 ? "Starting point" : "Not selected"}</span></summary><div className="mt-2 space-y-2">{i > 0 && <ContentDiff before={data.seed_skill ?? ""} after={candidate.skill} label="Changes from seed skill" />}<pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words bg-surface p-3 text-xs">{candidate.skill}</pre></div></details>)}
    {!data.candidates?.length && <p className="text-xs text-muted-foreground">No candidate results recorded yet.</p>}
  </>}</div>;
}

export default function GepaHistory({ runs }: { runs: GepaSummary[] }) {
  const [opened, setOpened] = useState<string | null>(null);
  return <section aria-label="GEPA experiments" className="mt-8 border-t border-border pt-4"><h2 className="m-0 text-sm font-semibold text-foreground">GEPA skill experiments</h2><p className="mt-1 text-xs text-muted-foreground">Workspace history. These trials generate skills; they are separate from live prompt experiments and aren’t linked to a recorded agent.</p>
    {!runs.length ? <p className="text-sm text-muted-foreground">No GEPA trials recorded yet.</p> : <div className="divide-y divide-border">{runs.map((run) => <div key={run.id}><button aria-expanded={opened === run.id} onClick={() => setOpened(opened === run.id ? null : run.id)} className="flex w-full items-center gap-3 py-3 text-left text-sm"><span className="text-muted-foreground">{opened === run.id ? "⌄" : "›"}</span><span className="font-medium">{run.skill_name ?? "Skill experiment"}</span><RecordBadge value={run.status} /><span className="flex-1 truncate text-xs text-muted-foreground">{run.task_model} · {run.reward_model_name} · {run.candidate_count ?? 0} candidates</span><span className="text-xs tabular-nums">{value(run.seed_score)} → {value(run.best_score)}</span><span className="text-xs text-muted-foreground">{date(run.created_at)}</span></button>{opened === run.id && <GepaTrial id={run.id} />}</div>)}</div>}
  </section>;
}
