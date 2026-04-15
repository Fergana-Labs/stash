"use client";

import { useEffect, useRef, useState } from "react";
import type { KnowledgeDensity } from "../../lib/types";

interface Props {
  data: KnowledgeDensity;
  onTopicClick?: (topic: string) => void;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  count: number;
  newestAt: string | null;
}

// Squarify treemap layout algorithm
function squarify(
  items: { label: string; count: number; newestAt: string | null }[],
  x: number,
  y: number,
  w: number,
  h: number,
): Rect[] {
  if (items.length === 0) return [];

  const total = items.reduce((s, i) => s + i.count, 0);
  if (total === 0) return [];

  const rects: Rect[] = [];
  let cx = x, cy = y, cw = w, ch = h;

  // Simple slice-and-dice with aspect ratio optimization
  const sorted = [...items].sort((a, b) => b.count - a.count);
  let remaining = total;

  for (let i = 0; i < sorted.length; i++) {
    const item = sorted[i];
    const ratio = item.count / remaining;

    let rw: number, rh: number, rx: number, ry: number;

    if (cw >= ch) {
      // Lay out horizontally
      rw = cw * ratio;
      rh = ch;
      rx = cx;
      ry = cy;
      cx += rw;
      cw -= rw;
    } else {
      // Lay out vertically
      rw = cw;
      rh = ch * ratio;
      rx = cx;
      ry = cy;
      cy += rh;
      ch -= rh;
    }

    remaining -= item.count;

    rects.push({
      x: rx,
      y: ry,
      w: rw,
      h: rh,
      label: item.label,
      count: item.count,
      newestAt: item.newestAt,
    });
  }

  return rects;
}

// Recency color: green for recent, slate for old
function recencyColor(newestAt: string | null): string {
  if (!newestAt) return "rgba(100, 116, 139, 0.4)"; // slate-500
  const age = Date.now() - new Date(newestAt).getTime();
  const days = age / (1000 * 60 * 60 * 24);
  if (days < 1) return "rgba(34, 197, 94, 0.7)";   // green — today
  if (days < 7) return "rgba(34, 197, 94, 0.5)";   // green — this week
  if (days < 30) return "rgba(34, 197, 94, 0.3)";  // green — this month
  if (days < 90) return "rgba(148, 163, 184, 0.3)"; // slate — quarter
  return "rgba(148, 163, 184, 0.15)";               // slate — old
}

interface TooltipInfo {
  x: number;
  y: number;
  label: string;
  count: number;
  newestAt: string | null;
}

export default function KnowledgeDensityMap({ data, onTopicClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rectsRef = useRef<Rect[]>([]);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const containerWidth = canvas.parentElement?.clientWidth || 400;
    const containerHeight = 320;
    const dpr = window.devicePixelRatio || 2;

    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = `${containerHeight}px`;
    ctx.scale(dpr, dpr);

    const pad = 4;
    const items = data.clusters.map((c) => ({
      label: c.label,
      count: c.count,
      newestAt: c.newest_at,
    }));

    const rects = squarify(items, pad, pad, containerWidth - pad * 2, containerHeight - pad * 2);
    rectsRef.current = rects;

    ctx.clearRect(0, 0, containerWidth, containerHeight);

    for (const rect of rects) {
      const gap = 1.5;
      const rx = rect.x + gap;
      const ry = rect.y + gap;
      const rw = rect.w - gap * 2;
      const rh = rect.h - gap * 2;

      if (rw < 2 || rh < 2) continue;

      // Fill with recency color
      ctx.fillStyle = recencyColor(rect.newestAt);
      ctx.beginPath();
      ctx.roundRect(rx, ry, rw, rh, 4);
      ctx.fill();

      // Border
      ctx.strokeStyle = "rgba(62, 78, 99, 0.4)";
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Label — always render, rotating for tall-thin rects
      const isWide = rw >= rh;
      const longSide = Math.max(rw, rh);
      const shortSide = Math.min(rw, rh);

      // Pick font size based on available space
      const fontSize = shortSide < 20 ? 8 : longSide < 50 ? 9 : 11;
      ctx.font = `500 ${fontSize}px 'JetBrains Mono', monospace`;
      ctx.fillStyle = "#F1F5F9";

      if (isWide || rw >= 30) {
        // Horizontal label
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        const maxChars = Math.floor((rw - 10) / (fontSize * 0.62));
        if (maxChars >= 2) {
          const label = rect.label.length > maxChars
            ? rect.label.slice(0, maxChars - 1) + "\u2026"
            : rect.label;
          ctx.fillText(label, rx + 5, ry + 4);
        }
      } else if (rh >= 30) {
        // Vertical (rotated) label for tall thin rects
        ctx.save();
        ctx.translate(rx + rw / 2, ry + rh - 5);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        const maxChars = Math.floor((rh - 10) / (fontSize * 0.62));
        if (maxChars >= 2) {
          const label = rect.label.length > maxChars
            ? rect.label.slice(0, maxChars - 1) + "\u2026"
            : rect.label;
          ctx.fillText(label, 0, 0);
        }
        ctx.restore();
      }
    }
  }, [data]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const r of rectsRef.current) {
      if (mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h) {
        setTooltip({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
          label: r.label,
          count: r.count,
          newestAt: r.newestAt,
        });
        return;
      }
    }
    setTooltip(null);
  };

  const handleClick = (e: React.MouseEvent) => {
    if (!onTopicClick) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    for (const r of rectsRef.current) {
      if (mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h) {
        onTopicClick(r.label);
        return;
      }
    }
  };

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="w-full cursor-pointer"
        style={{ height: 320 }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
        onClick={handleClick}
      />
      {tooltip && (
        <div
          className="absolute z-10 bg-base border border-border rounded-md px-3 py-2 pointer-events-none shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <div className="text-xs font-medium text-foreground">{tooltip.label}</div>
          <div className="text-[11px] text-muted mt-0.5">
            {tooltip.count} documents
          </div>
          {tooltip.newestAt && (
            <div className="text-[10px] text-muted mt-0.5">
              Latest: {new Date(tooltip.newestAt).toLocaleDateString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
