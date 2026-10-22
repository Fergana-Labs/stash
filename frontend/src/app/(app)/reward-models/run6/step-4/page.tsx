"use client";

import { useMemo, useState } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPage } from "@/components/reward-models/rm-ui";
import RewardTrendChart from "./_components/RewardTrendChart";
import { fleetDaily, generateHillClimbData, meanReward, totalRuns, type ClimbAgent, type DailyReward } from "./_components/mock-data";
import { cn } from "@/lib/utils";

const RANGES = [14, 30, 90] as const;
const COMPARE_DAYS = 7;
// A change smaller than this across the range is treated as noise.
const STEADY = 0.02;

type Trend = "improving" | "regressing" | "steady";
const trendOf = (change: number | null): Trend => change == null || Math.abs(change) < STEADY ? "steady" : change > 0 ? "improving" : "regressing";
const fmt = (n: number | null) => n == null ? "—" : n.toFixed(2);
const signed = (n: number | null) => n == null ? "—" : `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n).toFixed(2)}`;
const shortDate = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const clock = (t: number) => new Date(t).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

function summarize(daily: DailyReward[], from: number, to: number) {
  const start = meanReward(daily, from, from + COMPARE_DAYS);
  const end = meanReward(daily, to - COMPARE_DAYS, to);
  const change = start != null && end != null ? end - start : null;
  return { start, end, change, trend: trendOf(change), runs: totalRuns(daily, from, to) };
}

export default function HillClimbingPage() {
  useBreadcrumbs([{ label: "Hill climbing" }], "rm-hill-climbing");
  const data = useMemo(() => generateHillClimbData(), []);
  const [range, setRange] = useState<(typeof RANGES)[number]>(30);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lowOnly, setLowOnly] = useState(false);

  const to = data.days;
  const from = to - range;
  const fleet = useMemo(() => fleetDaily(data.agents, data.days), [data]);
  const fleetSummary = summarize(fleet, from, to);
  const rows = data.agents
    .map((agent) => ({ agent, ...summarize(agent.daily, from, to) }))
    .sort((a, b) => (b.change ?? 0) - (a.change ?? 0));
  const selected = data.agents.find((a) => a.id === selectedId) ?? null;
  const agentMean = new Map(rows.map((r) => [r.agent.id, r.end]));
  const runs = data.runs
    .filter((r) => !selected || r.agentId === selected.id)
    .filter((r) => !lowOnly || r.reward < 0.5)
    .slice(0, 12);
  const rangeStart = shortDate(data.dayStarts[from]);

  return (
    <RmPage
      wide
      title="Hill climbing"
      actions={<RangePicker value={range} onChange={setRange} />}
    >
      <section aria-labelledby="trend-heading" className="-mt-2">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <h2 id="trend-heading" className="m-0 text-[14px] font-medium">Reward over time</h2>
            <span className="text-[12px] text-muted-foreground">All agents <span className="font-mono text-foreground tabular-nums">{fmt(fleetSummary.end)}</span> last {COMPARE_DAYS} days · <TrendText change={fleetSummary.change} suffix={`since ${rangeStart}`} /> · {fleetSummary.runs.toLocaleString()} runs</span>
          </div>
          <Legend selected={selected} />
        </div>
        <RewardTrendChart agents={data.agents} fleet={fleet} dayStarts={data.dayStarts} from={from} selected={selected} />
      </section>

      <section aria-labelledby="agents-heading" className="mt-4">
        <h2 id="agents-heading" className="m-0 mb-2 text-[14px] font-medium">Agents</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="text-[12px] text-muted-foreground">
              <tr className="border-y border-border [&>th]:px-3 [&>th]:py-1.5 [&>th]:font-normal">
                <th>Agent</th><th>Reward model</th><th className="text-right">Reward, last {COMPARE_DAYS} days</th><th className="text-right">Change since {rangeStart}</th><th>Trend</th><th className="text-right">Runs</th><th className="text-right">Prompt</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const active = r.agent.id === selectedId;
                const latest = r.agent.promptChanges.at(-1);
                return (
                  <tr key={r.agent.id} aria-selected={active} onClick={() => setSelectedId(active ? null : r.agent.id)} className={cn("cursor-pointer border-b border-border-subtle h-8 [&>td]:px-3 [&>td]:py-0 [&>td]:leading-5", active ? "bg-brand-500/8" : "hover:bg-surface/60")}>
                    <td>
                      <button type="button" aria-pressed={active} onClick={(e) => { e.stopPropagation(); setSelectedId(active ? null : r.agent.id); }} className={cn("cursor-pointer text-left font-medium hover:underline", active && "text-brand-600")}>{r.agent.name}</button>
                    </td>
                    <td className="text-muted-foreground">{r.agent.rewardModel}</td>
                    <td className="text-right font-mono tabular-nums">{fmt(r.end)}</td>
                    <td className="text-right"><span className="inline-flex items-center gap-2"><Sparkline daily={r.agent.daily.slice(from, to)} trend={r.trend} /><span className="w-12 font-mono tabular-nums">{signed(r.change)}</span></span></td>
                    <td><TrendBadge trend={r.trend} /></td>
                    <td className="text-right tabular-nums text-muted-foreground">{r.runs.toLocaleString()}</td>
                    <td className="text-right text-muted-foreground" title={latest ? `v${latest.version}: ${latest.note}` : "Original prompt"}>v{(latest?.version ?? 1)}{latest && latest.day >= from && <span className="text-[11px]"> · {shortDate(data.dayStarts[latest.day])}</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="runs-heading" className="mt-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h2 id="runs-heading" className="m-0 text-[14px] font-medium">Recent runs{selected && <span className="font-normal text-muted-foreground"> · {selected.name}</span>}</h2>
          <div className="flex items-center gap-3 text-[12px]">
            {selected && <button type="button" onClick={() => setSelectedId(null)} className="cursor-pointer text-muted-foreground hover:text-foreground hover:underline">Show all agents</button>}
            <label className="flex cursor-pointer items-center gap-1.5 text-muted-foreground"><input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} className="accent-brand-500" />Reward below 0.50 only</label>
          </div>
        </div>
        {!runs.length ? <p className="border-y border-border py-6 text-center text-[13px] text-muted-foreground">No recent runs scored below 0.50{selected ? ` for ${selected.name}` : ""}.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[12px] text-muted-foreground">
                <tr className="border-y border-border [&>th]:px-3 [&>th]:py-1.5 [&>th]:font-normal">
                  <th>Finished</th><th>Task</th>{!selected && <th>Agent</th>}<th className="text-right">Reward</th><th className="text-right">vs. agent average</th><th className="text-right">Prompt</th><th className="text-right">Steps</th><th className="text-right">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const agent = data.agents.find((a) => a.id === run.agentId)!;
                  const diff = run.reward - (agentMean.get(run.agentId) ?? run.reward);
                  return (
                    <tr key={run.id} className="border-b border-border-subtle h-8 [&>td]:px-3 [&>td]:py-0 [&>td]:leading-5">
                      <td className="whitespace-nowrap text-muted-foreground tabular-nums">{clock(run.finishedAt)}</td>
                      <td>{run.task}</td>
                      {!selected && <td className="text-muted-foreground">{agent.name}</td>}
                      <td className="text-right"><RewardCell value={run.reward} /></td>
                      <td className={cn("text-right font-mono tabular-nums", diff <= -0.15 ? "text-red-700 dark:text-red-400" : "text-muted-foreground")}>{signed(diff)}</td>
                      <td className="text-right text-muted-foreground">v{run.promptVersion}</td>
                      <td className="text-right tabular-nums text-muted-foreground">{run.steps}</td>
                      <td className="text-right tabular-nums text-muted-foreground">{duration(run.durationSec)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </RmPage>
  );
}

function RangePicker({ value, onChange }: { value: number; onChange: (v: (typeof RANGES)[number]) => void }) {
  return (
    <div role="group" aria-label="Time range" className="flex rounded-md border border-border p-0.5 text-[12px]">
      {RANGES.map((r) => (
        <button key={r} type="button" aria-pressed={value === r} onClick={() => onChange(r)} className={cn("cursor-pointer rounded-[4px] px-2.5 py-1", value === r ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>{r} days</button>
      ))}
    </div>
  );
}

const TREND_STYLE: Record<Trend, { icon: typeof ArrowRight; label: string; className: string }> = {
  improving: { icon: ArrowUpRight, label: "Improving", className: "text-emerald-700 dark:text-emerald-400" },
  regressing: { icon: ArrowDownRight, label: "Regressing", className: "text-red-700 dark:text-red-400" },
  steady: { icon: ArrowRight, label: "Steady", className: "text-muted-foreground" },
};

function TrendText({ change, suffix }: { change: number | null; suffix: string }) {
  const style = TREND_STYLE[trendOf(change)];
  return <span className={cn("inline-flex items-center gap-1", style.className)}><style.icon className="size-3.5" aria-hidden="true" />{signed(change)} <span className="text-muted-foreground">{suffix}</span></span>;
}

function TrendBadge({ trend }: { trend: Trend }) {
  const style = TREND_STYLE[trend];
  return <span className={cn("inline-flex items-center gap-1 text-[12px]", style.className)}><style.icon className="size-3.5" aria-hidden="true" />{style.label}</span>;
}

function Sparkline({ daily, trend }: { daily: DailyReward[]; trend: Trend }) {
  const w = 64, h = 14;
  const values = daily.map((d) => d.mean);
  const lo = Math.min(...values), hi = Math.max(...values);
  const pts = values.map((v, i) => `${((i / Math.max(values.length - 1, 1)) * w).toFixed(1)},${(h - 2 - ((v - lo) / (hi - lo || 1)) * (h - 4)).toFixed(1)}`).join(" ");
  return <svg width={w} height={h} aria-hidden="true" className={TREND_STYLE[trend].className}><polyline points={pts} fill="none" stroke="currentColor" strokeWidth={1.25} /></svg>;
}

function Legend({ selected }: { selected: ClimbAgent | null }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-[12px] text-muted-foreground">
      {selected && <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 bg-[#2a78d6] dark:bg-[#3987e5]" />{selected.name}</span>}
      <span className="inline-flex items-center gap-1.5"><span className={cn("h-0.5 w-4", selected ? "border-t-2 border-foreground/70" : "bg-foreground/70")} />All agents (run-weighted)</span>
      <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-muted-foreground/40" />Each agent</span>
    </div>
  );
}

function RewardCell({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center justify-end gap-2">
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-surface"><span className={cn("block h-full rounded-full", value < 0.5 ? "bg-red-500/70" : "bg-foreground/40")} style={{ width: `${value * 100}%` }} /></span>
      <span className="w-9 font-mono tabular-nums">{value.toFixed(2)}</span>
    </span>
  );
}

function duration(sec: number) {
  return sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
}
