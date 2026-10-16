"use client";

import type { DifficultyBucket } from "@/lib/intuition-api";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const chars = (n: number) => n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);

/** Held-out accuracy by difficulty bucket (1 = shortest inputs, 10 = longest). */
export default function DifficultyChart({ buckets }: { buckets: DifficultyBucket[] }) {
  const points = buckets.filter((b) => b.accuracy != null && b.n > 0).sort((a, b) => a.bucket - b.bucket);
  if (points.length < 2) return null;
  const W = 320, H = 140, L = 30, R = 8, T = 8, B = 24;
  const x = (bucket: number) => L + ((bucket - 1) / 9) * (W - L - R);
  const y = (a: number) => T + (1 - a) * (H - T - B);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.bucket).toFixed(1)},${y(p.accuracy!).toFixed(1)}`).join(" ");
  return <figure className="m-0">
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[380px]" role="img" aria-label="Held-out accuracy by difficulty">
      {[0, 0.5, 1].map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={0.5} /><text x={L - 4} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground font-mono text-[8px]">{pct(t)}</text></g>)}
      <path d={path} fill="none" className="stroke-brand-500" strokeWidth={1.75} />
      {points.map((p) => <g key={p.bucket}>
        <title>{`Difficulty ${p.bucket}: ${pct(p.accuracy!)} on ${p.n} examples (${chars(p.difficulty[0])}–${chars(p.difficulty[1])} characters)`}</title>
        <circle cx={x(p.bucket)} cy={y(p.accuracy!)} r={2.6} className="fill-brand-500" />
      </g>)}
      {Array.from({ length: 10 }, (_, i) => i + 1).map((b) => <text key={b} x={x(b)} y={H - 10} textAnchor="middle" className="fill-muted-foreground font-mono text-[8px]">{b}</text>)}
    </svg>
    <figcaption className="mt-1 text-[11px] text-muted-foreground">Accuracy by difficulty: 1 = shortest inputs, 10 = longest (by characters).</figcaption>
  </figure>;
}
