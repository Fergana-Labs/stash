"use client";

import { useEffect, useRef, useState } from "react";
import type { ActivityTimeline } from "../../lib/types";

interface Props {
  data: ActivityTimeline;
}

const CELL_SIZE = 14;
const CELL_GAP = 2;
const LABEL_WIDTH = 80;
const PADDING = 16;

// Orange intensity scale matching brand color
const INTENSITY_COLORS = [
  "rgba(249, 115, 22, 0.0)",   // 0: transparent
  "rgba(249, 115, 22, 0.15)",  // low
  "rgba(249, 115, 22, 0.35)",  // medium-low
  "rgba(249, 115, 22, 0.55)",  // medium
  "rgba(249, 115, 22, 0.75)",  // medium-high
  "rgba(249, 115, 22, 1.0)",   // high
];

function getIntensity(count: number, maxCount: number): number {
  if (count === 0) return 0;
  if (maxCount === 0) return 0;
  const ratio = count / maxCount;
  if (ratio <= 0.1) return 1;
  if (ratio <= 0.25) return 2;
  if (ratio <= 0.5) return 3;
  if (ratio <= 0.75) return 4;
  return 5;
}

interface TooltipInfo {
  x: number;
  y: number;
  agent: string;
  date: string;
  total: number;
  byType: Record<string, number>;
}

export default function AgentActivityTimeline({ data }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  // Compute max count for intensity scaling
  const maxCount = data.buckets.reduce((max, b) => {
    for (const agent of Object.values(b.agents)) {
      if (agent.total > max) max = agent.total;
    }
    return max;
  }, 0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const agents = data.agents;
    const buckets = data.buckets;

    const totalWidth = LABEL_WIDTH + PADDING + buckets.length * (CELL_SIZE + CELL_GAP);
    const totalHeight = PADDING + agents.length * (CELL_SIZE + CELL_GAP) + PADDING;

    const dpr = window.devicePixelRatio || 2;
    canvas.width = totalWidth * dpr;
    canvas.height = totalHeight * dpr;
    canvas.style.width = `${totalWidth}px`;
    canvas.style.height = `${totalHeight}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, totalWidth, totalHeight);

    // Agent labels (violet)
    ctx.font = "500 11px 'JetBrains Mono', monospace";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#8B5CF6";

    for (let i = 0; i < agents.length; i++) {
      const y = PADDING + i * (CELL_SIZE + CELL_GAP) + CELL_SIZE / 2;
      const label = agents[i].length > 10 ? agents[i].slice(0, 9) + "..." : agents[i];
      ctx.fillText(label, LABEL_WIDTH, y);
    }

    // Grid cells
    for (let bi = 0; bi < buckets.length; bi++) {
      const bucket = buckets[bi];
      const x = LABEL_WIDTH + PADDING + bi * (CELL_SIZE + CELL_GAP);

      for (let ai = 0; ai < agents.length; ai++) {
        const y = PADDING + ai * (CELL_SIZE + CELL_GAP);
        const agentData = bucket.agents[agents[ai]];
        const count = agentData?.total ?? 0;
        const intensity = getIntensity(count, maxCount);

        // Cell background
        if (intensity === 0) {
          ctx.fillStyle = "rgba(148, 163, 184, 0.08)";
        } else {
          ctx.fillStyle = INTENSITY_COLORS[intensity];
        }

        // Rounded rect
        const r = 2;
        ctx.beginPath();
        ctx.roundRect(x, y, CELL_SIZE, CELL_SIZE, r);
        ctx.fill();
      }
    }
  }, [data, maxCount]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.clientWidth / (LABEL_WIDTH + PADDING + data.buckets.length * (CELL_SIZE + CELL_GAP));
    const mx = (e.clientX - rect.left) / scaleX;
    const my = (e.clientY - rect.top) / scaleX;

    const bi = Math.floor((mx - LABEL_WIDTH - PADDING) / (CELL_SIZE + CELL_GAP));
    const ai = Math.floor((my - PADDING) / (CELL_SIZE + CELL_GAP));

    if (bi >= 0 && bi < data.buckets.length && ai >= 0 && ai < data.agents.length) {
      const bucket = data.buckets[bi];
      const agent = data.agents[ai];
      const agentData = bucket.agents[agent];
      if (agentData && agentData.total > 0) {
        setTooltip({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          agent,
          date: bucket.date.split("T")[0],
          total: agentData.total,
          byType: agentData.by_type,
        });
        return;
      }
    }
    setTooltip(null);
  };

  return (
    <div ref={containerRef} className="relative overflow-x-auto">
      <canvas
        ref={canvasRef}
        className="cursor-crosshair"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
      />
      {tooltip && (
        <div
          className="absolute z-10 bg-base border border-border rounded-md px-3 py-2 pointer-events-none shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <div className="text-xs font-medium text-foreground">
            <span className="text-violet-400">{tooltip.agent}</span>
            <span className="text-muted mx-1">&middot;</span>
            <span className="text-muted font-mono">{tooltip.date}</span>
          </div>
          <div className="text-[11px] text-muted mt-1">
            {tooltip.total} events
          </div>
          <div className="mt-1 space-y-0.5">
            {Object.entries(tooltip.byType).map(([type, count]) => (
              <div key={type} className="flex justify-between gap-4 text-[10px]">
                <span className="text-muted font-mono">{type}</span>
                <span className="text-foreground">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
