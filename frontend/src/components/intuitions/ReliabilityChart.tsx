"use client";

import type { Evaluation } from "@/lib/intuition-api";
import { pct } from "./im-helpers";

const W = 260;
const H = 150;
const PAD = { l: 30, r: 8, t: 8, b: 22 };

/**
 * Reliability diagram: for each confidence bin, the bar is observed accuracy and the tick is
 * mean confidence. A calibrated model's bars meet the dashed diagonal.
 */
export default function ReliabilityChart({ bins }: { bins: NonNullable<Evaluation["reliability"]> }) {
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const x = (v: number) => PAD.l + v * iw;
  const y = (v: number) => PAD.t + (1 - v) * ih;
  const bw = iw / 10;
  const total = bins.reduce((s, b) => s + b.n, 0);

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-[340px]" role="img" aria-label="Reliability diagram: accuracy versus confidence per bin">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={0.5} />
            <text x={PAD.l - 4} y={y(t) + 3} textAnchor="end" className="fill-muted-foreground font-mono text-[8px]">
              {t * 100}%
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((t) => (
          <text key={t} x={x(t)} y={H - 8} textAnchor="middle" className="fill-muted-foreground font-mono text-[8px]">
            {t * 100}%
          </text>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="stroke-muted-foreground" strokeDasharray="3 3" strokeWidth={0.75} />
        {bins.map((b) => (
          <g key={b.bin}>
            <title>{`${b.bin * 10}–${b.bin * 10 + 10}% confidence: ${b.n} examples, mean confidence ${pct(b.confidence)}, accuracy ${pct(b.accuracy)}`}</title>
            <rect
              x={x(b.bin / 10) + 1.5}
              width={bw - 3}
              y={y(b.accuracy)}
              height={Math.max(0, y(0) - y(b.accuracy))}
              className="fill-brand-500"
              fillOpacity={0.25 + 0.6 * Math.min(1, b.n / Math.max(1, total / 4))}
              rx={1.5}
            />
            <line x1={x(b.bin / 10) + 1.5} x2={x(b.bin / 10) + bw - 1.5} y1={y(b.confidence)} y2={y(b.confidence)} className="stroke-foreground" strokeWidth={1.25} />
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-[11px] text-muted-foreground">Bars: accuracy per confidence bin (darker = more examples). Ticks: mean confidence.</figcaption>
    </figure>
  );
}
