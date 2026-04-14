"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { EmbeddingProjection, EmbeddingProjectionPoint } from "../../lib/types";

interface Props {
  data: EmbeddingProjection;
  onPointClick?: (point: EmbeddingProjectionPoint) => void;
}

const SOURCE_COLORS: Record<string, string> = {
  history_events: "#8B5CF6",  // violet — agent
  notebook_pages: "#22C55E",  // green
  table_rows: "#3B82F6",      // blue
};

const SOURCE_LABELS: Record<string, string> = {
  history_events: "History",
  notebook_pages: "Notebooks",
  table_rows: "Tables",
};

interface TooltipInfo {
  x: number;
  y: number;
  point: EmbeddingProjectionPoint;
}

export default function EmbeddingSpaceExplorer({ data, onPointClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  // Pan/zoom state
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const draggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });

  const toScreen = useCallback((px: number, py: number, w: number, h: number) => {
    const zoom = zoomRef.current;
    const pan = panRef.current;
    const cx = w / 2 + pan.x;
    const cy = h / 2 + pan.y;
    const scale = Math.min(w, h) * 0.4 * zoom;
    return {
      sx: cx + px * scale,
      sy: cy + py * scale,
    };
  }, []);

  const draw = useCallback(() => {
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

    ctx.clearRect(0, 0, containerWidth, containerHeight);

    // Draw points
    const radius = 3.5;
    for (const point of data.points) {
      const { sx, sy } = toScreen(point.x, point.y, containerWidth, containerHeight);

      // Skip if off-screen
      if (sx < -10 || sx > containerWidth + 10 || sy < -10 || sy > containerHeight + 10) continue;

      ctx.beginPath();
      ctx.arc(sx, sy, radius, 0, Math.PI * 2);
      ctx.fillStyle = SOURCE_COLORS[point.source] || "#94A3B8";
      ctx.globalAlpha = 0.7;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    // Legend
    const legendX = containerWidth - 120;
    const legendY = 16;
    ctx.font = "500 10px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";

    const sources = [...new Set(data.points.map((p) => p.source))];
    for (let i = 0; i < sources.length; i++) {
      const s = sources[i];
      const y = legendY + i * 18;

      ctx.beginPath();
      ctx.arc(legendX, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = SOURCE_COLORS[s] || "#94A3B8";
      ctx.fill();

      ctx.fillStyle = "#94A3B8";
      ctx.fillText(SOURCE_LABELS[s] || s, legendX + 10, y);
    }

    // Stats
    ctx.font = "400 10px 'JetBrains Mono', monospace";
    ctx.fillStyle = "#64748B";
    ctx.textAlign = "left";
    ctx.fillText(
      `${data.stats.projected} / ${data.stats.total_embeddings} points`,
      8,
      containerHeight - 8,
    );
  }, [data, toScreen]);

  useEffect(() => {
    draw();
  }, [draw]);

  const findPoint = useCallback(
    (mx: number, my: number): EmbeddingProjectionPoint | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const hitRadius = 8;

      for (const point of data.points) {
        const { sx, sy } = toScreen(point.x, point.y, w, h);
        const dx = mx - sx;
        const dy = my - sy;
        if (dx * dx + dy * dy < hitRadius * hitRadius) {
          return point;
        }
      }
      return null;
    },
    [data, toScreen],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (draggingRef.current) {
        panRef.current = {
          x: panRef.current.x + (mx - lastMouseRef.current.x),
          y: panRef.current.y + (my - lastMouseRef.current.y),
        };
        lastMouseRef.current = { x: mx, y: my };
        draw();
        setTooltip(null);
        return;
      }

      const point = findPoint(mx, my);
      if (point) {
        setTooltip({ x: mx, y: my, point });
      } else {
        setTooltip(null);
      }
    },
    [draw, findPoint],
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      zoomRef.current = Math.max(0.3, Math.min(10, zoomRef.current * delta));
      draw();
    },
    [draw],
  );

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    draggingRef.current = true;
    lastMouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }, []);

  const handleMouseUp = useCallback(() => {
    draggingRef.current = false;
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!onPointClick) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const point = findPoint(e.clientX - rect.left, e.clientY - rect.top);
      if (point) onPointClick(point);
    },
    [findPoint, onPointClick],
  );

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="w-full cursor-grab active:cursor-grabbing"
        style={{ height: 320 }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => {
          setTooltip(null);
          draggingRef.current = false;
        }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onClick={handleClick}
      />
      {tooltip && (
        <div
          className="absolute z-10 bg-base border border-border rounded-md px-3 py-2 pointer-events-none shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <div className="text-xs font-medium text-foreground">{tooltip.point.label}</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: SOURCE_COLORS[tooltip.point.source] }}
            />
            <span className="text-[10px] text-muted">
              {SOURCE_LABELS[tooltip.point.source] || tooltip.point.source}
            </span>
          </div>
          {tooltip.point.created_at && (
            <div className="text-[10px] text-muted mt-0.5">
              {new Date(tooltip.point.created_at).toLocaleDateString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
