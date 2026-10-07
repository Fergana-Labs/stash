"use client";

import type { PromptRevision, Trend } from "@/lib/optimization-api";

const COLORS = ["#ea580c", "#2563eb", "#16a34a", "#9333ea", "#0891b2", "#db2777"];
export const number = (n: number | null | undefined) => n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 3 });

export default function TrendChart({ title, subtitle, data, revisions, metric, range }: {
  title: string; subtitle: string; data: Trend[]; revisions: PromptRevision[]; metric: "reward" | "business"; range: [number, number];
}) {
  const points = data.filter((p) => p[metric] != null);
  const days = [...new Set(data.map((p) => p.day))].sort();
  const x = (day: string) => 54 + (days.length > 1 ? days.indexOf(day) / (days.length - 1) * 448 : 224);
  const y = (value: number) => 160 - ((value - range[0]) / (range[1] - range[0])) * 130;
  const active = revisions.filter((r) => points.some((p) => p.revision_id === r.id));
  return <section aria-label={title} className="rounded-xl border border-border p-5">
    <h2 className="m-0 text-sm font-medium">{title}</h2><p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
    {points.length === 0 ? <div className="flex h-48 items-center justify-center text-center text-sm text-muted-foreground">{metric === "reward" ? "Reward appears after real runs are scored." : "Report business outcomes to see this trend."}</div> : <>
      <svg role="img" aria-label={`${title} by UTC date and prompt version`} viewBox="0 0 530 200" className="w-full overflow-visible">
        {[range[0], (range[0] + range[1]) / 2, range[1]].map((tick) => <g key={tick}><line x1={54} x2={502} y1={y(tick)} y2={y(tick)} stroke="currentColor" opacity={0.12} /><text x={46} y={y(tick) + 4} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.6}>{number(tick)}</text></g>)}
        {active.map((r) => { const rows = points.filter((p) => p.revision_id === r.id); const color = COLORS[(r.version - 1) % COLORS.length]; return <g key={r.id}><polyline points={rows.map((p) => `${x(p.day)},${y(p[metric]!)}`).join(" ")} fill="none" stroke={color} strokeWidth={2} />{rows.map((p) => <circle key={p.day} cx={x(p.day)} cy={y(p[metric]!)} r={4} fill={color}><title>{p.day} · v{r.version}: {number(p[metric])} · {metric === "reward" ? p.scored : p.measured} measured / {p.assigned} assigned</title></circle>)}</g>; })}
        <text x={54} y={187} fontSize={10} fill="currentColor" opacity={0.6}>{days[0]}</text>{days.length > 1 && <text x={502} y={187} textAnchor="end" fontSize={10} fill="currentColor" opacity={0.6}>{days.at(-1)}</text>}
      </svg>
      <div className="flex flex-wrap gap-3 text-xs">{active.map((r) => <span key={r.id} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[(r.version - 1) % COLORS.length] }} />v{r.version}</span>)}</div>
      <details className="mt-3 text-xs text-muted-foreground"><summary className="cursor-pointer">View measurements</summary><table className="mt-2 w-full text-left"><thead><tr><th>Date (UTC)</th><th>Prompt</th><th>Mean</th><th>Measured / assigned</th></tr></thead><tbody>{data.map((p) => <tr key={`${p.day}-${p.revision_id}`}><td className="py-1">{p.day}</td><td>v{revisions.find((r) => r.id === p.revision_id)?.version}</td><td>{number(p[metric])}</td><td>{metric === "reward" ? p.scored : p.measured} / {p.assigned}</td></tr>)}</tbody></table></details>
    </>}
  </section>;
}
