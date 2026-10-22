"use client";

import Link from "next/link";
import type { RewardHistory } from "@/lib/monitoring-api";
import type { OptimizationDetail } from "@/lib/optimization-api";

const colors = ["#f97316", "#2563eb", "#0d9488", "#9333ea", "#db2777"];
export const value = (n: number | null | undefined) => n == null ? "—" : n.toFixed(3);
export const signed = (n: number) => `${n > 0 ? "+" : ""}${value(n)}`;
export const date = (s: string) => new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function RollingRewardChart({ data, program }: { data: RewardHistory; program: OptimizationDetail | null }) {
  const points = data.points;
  const first = points.length ? new Date(points[0].recorded_at).getTime() : 0;
  const last = points.length ? new Date(points.at(-1)!.recorded_at).getTime() : 0;
  const x = (s: string) => 55 + (last === first ? 400 : (new Date(s).getTime() - first) / (last - first) * 800);
  const means = points.map((p) => p.rolling_mean);
  const min = data.unit === "action_credit" ? -1 : Math.min(...means, 0);
  const max = data.unit === "action_credit" ? 1 : Math.max(...means, 1);
  const y = (n: number) => 184 - (n - min) / (max - min || 1) * 150;
  const series = [...new Set(points.map((p) => p.revision_id))];
  const name = (id: string | null) => id ? `Prompt v${program?.revisions.find((r) => r.id === id)?.version ?? "?"}` : "Recorded runs";
  const markers = [
    ...(program?.rounds.filter((r) => r.status === "promoted" && r.finished_at).map((r) => ({ kind: "promoted", created_at: r.finished_at!, label: `${name(r.candidate_id)} accepted` })) ?? []),
    ...(program?.events.filter((e) => e.kind === "rollback").map((e) => ({ ...e, label: "Rolled back" })) ?? []),
  ].filter((e) => new Date(e.created_at).getTime() >= first && new Date(e.created_at).getTime() <= last);
  return <figure className="m-0 border-y border-border py-4" aria-label="Rolling reward">
    <div className="flex flex-wrap items-center justify-between gap-2"><figcaption className="text-sm font-medium">Reward over time</figcaption><span className="text-xs text-muted-foreground">{data.total} scored runs in total</span></div>
    <p className="mt-1 text-xs text-muted-foreground">{data.unit === "action_credit" ? "Mean action credit per run (−1 to +1)." : data.unit === "eval_probability" ? "Probability the eval decides success, per run (0 to 1)." : "Mean trace reward."} {program ? "By task assignment date." : "By trace recording date."} Each point averages up to {data.window} recent scored runs{program ? " with the same prompt" : ""}, using all available runs when there are fewer.</p>
    {!points.length ? <p className="flex h-44 items-center justify-center text-sm text-muted-foreground">{program ? "No completed experiment runs have a reward yet." : "No saved rewards from this model for this agent yet."}</p> : <>
      <svg viewBox="0 0 900 222" className="h-56 w-full" role="img" aria-label="Rolling mean reward by recorded run date">
        {[min, (min + max) / 2, max].map((tick) => <g key={tick}><line x1={55} x2={855} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.1} /><text x={44} y={y(tick) + 4} fontSize={11} fill="currentColor" opacity={0.55} textAnchor="end">{tick.toFixed(1)}</text></g>)}
        {markers.map((e, i) => <g key={`${e.created_at}-${i}`}><line x1={x(e.created_at)} x2={x(e.created_at)} y1={20} y2={184} stroke="currentColor" opacity={0.35} strokeDasharray="4 4" /><text x={x(e.created_at)} y={13 + (i % 2) * 12} fontSize={10} textAnchor="middle" fill="currentColor">{e.label}</text><title>{new Date(e.created_at).toLocaleString()}, {e.kind === "promoted" ? "Candidate accepted for future assignments" : "Prompt rolled back"}</title></g>)}
        {series.map((id, i) => { const rows = points.filter((p) => p.revision_id === id); return <g key={id ?? "observed"}><polyline points={rows.map((p) => `${x(p.recorded_at)},${y(p.rolling_mean)}`).join(" ")} stroke={colors[i % colors.length]} strokeWidth={2} fill="none" />{rows.map((p) => <circle key={p.id} cx={x(p.recorded_at)} cy={y(p.rolling_mean)} r={3} fill={colors[i % colors.length]}><title>{p.title}, {name(id)}, mean {value(p.rolling_mean)} across {p.window_count} runs, this run {value(p.reward)}</title></circle>)}</g>; })}
        <text x={55} y={211} fontSize={11} fill="currentColor" opacity={0.55}>{date(points[0].recorded_at)}</text><text x={855} y={211} fontSize={11} textAnchor="end" fill="currentColor" opacity={0.55}>{date(points.at(-1)!.recorded_at)}</text>
      </svg>
      <div className="flex flex-wrap gap-4 text-xs">{series.map((id, i) => <span key={id ?? "observed"} className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colors[i % colors.length] }} />{name(id)}{id && id === data.active_revision_id ? ", current" : ""}</span>)}</div>
      <details className="mt-3 text-xs"><summary className="cursor-pointer text-muted-foreground">View chart measurements</summary><div className="mt-2 max-h-64 overflow-auto"><table className="w-full text-left"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-2">Run</th><th>Prompt</th><th className="text-right">Reward</th><th className="text-right">Rolling mean / runs</th></tr></thead><tbody>{points.map((p) => <tr key={p.id} className="border-b border-border-subtle"><td className="py-2">{p.trace_id ? <Link href={`/reward-models/traces/${p.trace_id}`} className="hover:underline">{p.title}</Link> : p.title}</td><td>{p.revision_id ? name(p.revision_id) : "Not recorded"}</td><td className="text-right tabular-nums">{value(p.reward)}</td><td className="text-right tabular-nums">{value(p.rolling_mean)} / {p.window_count}</td></tr>)}</tbody></table></div>{points.length < data.total && <p className="text-muted-foreground">Chart samples the full history; each rolling mean uses the underlying runs.</p>}</details>
    </>}
    <p className="mb-0 mt-3 text-xs text-muted-foreground">This trend reflects the tasks the agent ran. Prompt experiment comparisons below measure candidate performance against the baseline.</p>
  </figure>;
}
