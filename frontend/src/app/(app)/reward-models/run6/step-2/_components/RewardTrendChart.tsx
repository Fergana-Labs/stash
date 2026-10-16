"use client";

import { useEffect, useRef, useState } from "react";
import type { ClimbAgent, DailyReward } from "./mock-data";

const H = 180;
const PAD = { top: 18, right: 16, bottom: 24, left: 36 };
const day = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** Daily mean reward: all agents (thin, muted), the run-weighted fleet mean, and the selected agent highlighted. */
export default function RewardTrendChart({ agents, fleet, dayStarts, from, selected }: {
  agents: ClimbAgent[]; fleet: DailyReward[]; dayStarts: number[]; from: number; selected: ClimbAgent | null;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const to = fleet.length;
  const visible = (d: DailyReward[]) => d.slice(from, to);
  const values = agents.flatMap((a) => visible(a.daily).map((d) => d.mean));
  const lo = Math.floor(Math.min(...values) * 10) / 10;
  const hi = Math.ceil(Math.max(...values) * 10) / 10;
  const ticks = Array.from({ length: Math.round((hi - lo) * 10) + 1 }, (_, i) => lo + i / 10).filter((_, i, all) => all.length <= 6 || i % 2 === 0);
  const innerW = Math.max(width - PAD.left - PAD.right, 10);
  const x = (d: number) => PAD.left + ((d - from) / Math.max(to - 1 - from, 1)) * innerW;
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);
  const path = (d: DailyReward[]) => visible(d).map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p.mean).toFixed(1)}`).join("");
  const labelDays = [from, Math.round((from + to - 1) / 2), to - 1];
  const changes = selected?.promptChanges.filter((c) => c.day >= from) ?? [];

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const d = Math.round(from + ((e.clientX - rect.left - PAD.left) / innerW) * (to - 1 - from));
    setHover(Math.min(Math.max(d, from), to - 1));
  };
  const tipLeft = hover == null ? 0 : Math.min(Math.max(x(hover) + 12, 0), width - 200);

  return (
    <div ref={ref} className="relative">
      <svg width={width} height={H} role="img" aria-label={`Daily mean reward${selected ? ` for ${selected.name} and` : " for"} all agents`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} className="block select-none">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className="stroke-border" />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className="fill-muted-foreground text-[11px] tabular-nums">{t.toFixed(1)}</text>
          </g>
        ))}
        {labelDays.map((d, i) => <text key={d} x={x(d)} y={H - 8} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"} className="fill-muted-foreground text-[11px]">{day(dayStarts[d])}</text>)}
        {changes.map((c) => (
          <g key={c.version}>
            <line x1={x(c.day)} x2={x(c.day)} y1={PAD.top - 6} y2={H - PAD.bottom} strokeDasharray="3 3" className="stroke-muted-foreground/50" />
            <text x={x(c.day) + 4} y={PAD.top - 10} className="fill-muted-foreground text-[10.5px]">v{c.version}</text>
          </g>
        ))}
        {agents.filter((a) => a !== selected).map((a) => <path key={a.id} d={path(a.daily)} fill="none" strokeWidth={1} className="stroke-muted-foreground/25" />)}
        <path d={path(fleet)} fill="none" strokeWidth={2} strokeDasharray={selected ? "5 3" : undefined} className="stroke-foreground/70" />
        {selected && <path d={path(selected.daily)} fill="none" strokeWidth={2} className="stroke-[#2a78d6] dark:stroke-[#3987e5]" />}
        {hover != null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={H - PAD.bottom} className="stroke-foreground/30" />
            <circle cx={x(hover)} cy={y(fleet[hover].mean)} r={4} strokeWidth={2} className="fill-foreground/70 stroke-background" />
            {selected && <circle cx={x(hover)} cy={y(selected.daily[hover].mean)} r={4} strokeWidth={2} className="fill-[#2a78d6] stroke-background dark:fill-[#3987e5]" />}
          </g>
        )}
      </svg>
      {hover != null && (
        <div className="pointer-events-none absolute top-2 w-48 rounded-md border border-border bg-background px-3 py-2 text-[12px] shadow-sm" style={{ left: tipLeft }}>
          <p className="m-0 mb-1 font-medium">{day(dayStarts[hover])}</p>
          {selected && <Row swatch="bg-[#2a78d6] dark:bg-[#3987e5]" label={selected.name} value={selected.daily[hover].mean} runs={selected.daily[hover].runs} />}
          <Row swatch="bg-foreground/70" label="All agents" value={fleet[hover].mean} runs={fleet[hover].runs} />
        </div>
      )}
    </div>
  );
}

function Row({ swatch, label, value, runs }: { swatch: string; label: string; value: number; runs: number }) {
  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className={`h-2 w-2 shrink-0 rounded-full ${swatch}`} />
      <span className="min-w-0 flex-1 truncate text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value.toFixed(2)}</span>
      <span className="w-12 text-right text-[11px] text-muted-foreground tabular-nums">{runs.toLocaleString()}</span>
    </div>
  );
}
