"use client";

import Link from "next/link";
import type { OptimizationDetail } from "@/lib/optimization-api";
import ContentDiff from "@/components/workbench/ContentDiff";
import { RecordBadge } from "@/components/workbench/workbench-ui";
import { date, signed, value } from "./RollingRewardChart";

export default function PromptEvolution({ program }: { program: OptimizationDetail }) {
  const version = (id: string | null) => program.revisions.find((r) => r.id === id)?.version;
  return <section id="prompt-optimization" aria-label="Prompt evolution" className="mt-6 scroll-mt-4">
    <div className="mb-1 flex items-center justify-between gap-2"><h2 className="m-0 text-sm font-semibold text-foreground">Prompt evolution</h2><Link className="text-xs text-muted-foreground hover:text-foreground hover:underline" href={`/reward-models/optimization/${program.id}`}>Manage optimization →</Link></div>
    <p className="mt-1 text-xs text-muted-foreground">{program.scope} · {program.reward_model.name} · Supplementary instruction history for this workload.</p>
    {program.error && <p role="alert" className="text-sm text-red-600">{program.error}</p>}
    <div className="divide-y divide-border border-y border-border">{[...program.revisions].reverse().map((revision) => {
      const round = program.rounds.find((r) => r.candidate_id === revision.id);
      const baseline = program.revisions.find((r) => r.id === round?.baseline_id);
      const stats = program.revision_stats?.find((r) => r.revision_id === revision.id);
      const status = round?.status === "promoted" ? "accepted" : round?.status === "collecting" ? "testing" : round?.status === "generating" ? "proposing" : round?.status ?? "original";
      return <details key={revision.id} className="group py-3"><summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 text-sm"><span className="text-muted-foreground group-open:rotate-90">›</span><span className="font-medium">v{revision.version}</span><RecordBadge value={status} />{revision.id === program.active_revision_id && <span className="text-xs text-emerald-700">Current</span>}<span className="min-w-0 flex-1 truncate text-muted-foreground">{revision.rationale}</span><span className="text-xs text-muted-foreground">{date(revision.created_at)}</span></summary><div className="mt-3 space-y-3 pl-6">
        <p className="m-0 text-sm">{revision.rationale}</p>
        <p className="text-xs text-muted-foreground">{round?.status === "promoted" && round.finished_at && `Accepted ${new Date(round.finished_at).toLocaleString()} · `}{stats ? `${stats.assigned} assigned runs · ${stats.completed} scored runs · mean reward ${value(stats.reward)}` : "No runs assigned to this prompt yet."}</p>
        {baseline && <ContentDiff before={baseline.content} after={revision.content} label={`Changes from baseline v${baseline.version}`} />}
        <details className="text-xs"><summary className="cursor-pointer">Full prompt</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words bg-surface p-3 text-xs leading-relaxed">{revision.content || "No supplementary instructions; the agent uses its existing prompt."}</pre></details>
      </div></details>;
    })}</div>
    <h3 className="mb-2 mt-6 text-sm font-medium text-foreground">Experiments</h3>
    {!program.rounds.length ? <p className="text-sm text-muted-foreground">No candidate has been proposed yet.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-2">Trial</th><th>Decision</th><th>Baseline reward</th><th>Candidate reward</th><th>Change</th>{program.metric && <th>Business result</th>}</tr></thead><tbody>{program.rounds.map((r) => <tr key={r.id} className="border-b border-border-subtle align-top"><td className="py-3 pr-3">#{r.number} · v{version(r.baseline_id)} → {r.candidate_id ? `v${version(r.candidate_id)}` : "proposing"}</td><td className="max-w-72 py-3 pr-4"><RecordBadge value={r.status === "promoted" ? "accepted" : r.status === "collecting" ? "testing" : r.status} /><p className="mb-0 mt-1 leading-relaxed text-muted-foreground">{r.report?.reason ?? r.error ?? "Waiting for candidate instructions."}</p></td><td className="py-3 pr-3 tabular-nums">{value(r.report?.arms.baseline?.reward.mean)}<span className="mt-1 block text-muted-foreground">{r.report?.arms.baseline?.completed ?? 0} / {program.runs_per_arm} scored</span></td><td className="py-3 pr-3 tabular-nums">{value(r.report?.arms.candidate?.reward.mean)}<span className="mt-1 block text-muted-foreground">{r.report?.arms.candidate?.completed ?? 0} / {program.runs_per_arm} scored</span></td><td className="py-3 pr-3 tabular-nums">{r.report?.reward_change?.mean != null ? signed(r.report.reward_change.mean) : "—"}<span className="mt-1 block whitespace-nowrap text-muted-foreground">{r.report?.reward_change?.low != null ? `99% interval ${value(r.report.reward_change.low)} to ${value(r.report.reward_change.high)}` : "Awaiting comparison"}</span></td>{program.metric && <td className="py-3 tabular-nums">{value(r.report?.arms.baseline?.business.mean)} → {value(r.report?.arms.candidate?.business.mean)}<span className="mt-1 block text-muted-foreground">{program.metric.name} · {r.report?.arms.candidate?.business.n ?? 0} candidate outcomes</span></td>}</tr>)}</tbody></table></div>}
  </section>;
}
