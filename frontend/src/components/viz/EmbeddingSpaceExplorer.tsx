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

// Rotate a 3D point around the Y axis, then X axis
function rotatePoint(
  px: number, py: number, pz: number,
  rotY: number, rotX: number,
): [number, number, number] {
  // Y-axis rotation
  const cosY = Math.cos(rotY);
  const sinY = Math.sin(rotY);
  const x1 = px * cosY + pz * sinY;
  const z1 = -px * sinY + pz * cosY;

  // X-axis rotation
  const cosX = Math.cos(rotX);
  const sinX = Math.sin(rotX);
  const y1 = py * cosX - z1 * sinX;
  const z2 = py * sinX + z1 * cosX;

  return [x1, y1, z2];
}

export default function EmbeddingSpaceExplorer({ data, onPointClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  // Rotation state (radians)
  const rotYRef = useRef(0.4);
  const rotXRef = useRef(0.3);
  const draggingRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const autoRotateRef = useRef(true);
  const animRef = useRef<number>(0);

  // Project a 3D point to 2D screen coordinates with perspective
  const project = useCallback(
    (px: number, py: number, pz: number, w: number, h: number) => {
      const [rx, ry, rz] = rotatePoint(px, py, pz, rotYRef.current, rotXRef.current);

      const fov = 3;
      const viewDist = fov + rz;
      const scale = Math.min(w, h) * 0.35 * (fov / Math.max(viewDist, 0.5));

      return {
        sx: w / 2 + rx * scale,
        sy: h / 2 + ry * scale,
        depth: rz,
      };
    },
    [],
  );

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

    // Sort points by depth (back to front) for correct overlap
    const projected = data.points.map((point) => {
      const { sx, sy, depth } = project(point.x, point.y, point.z, containerWidth, containerHeight);
      return { point, sx, sy, depth };
    });
    projected.sort((a, b) => a.depth - b.depth);

    // Draw axes (faint guide lines through origin)
    const axisLen = 0.8;
    const axes = [
      { dir: [axisLen, 0, 0] as const, label: "PC1", color: "#475569" },
      { dir: [0, axisLen, 0] as const, label: "PC2", color: "#475569" },
      { dir: [0, 0, axisLen] as const, label: "PC3", color: "#475569" },
    ];
    for (const axis of axes) {
      const start = project(-axis.dir[0], -axis.dir[1], -axis.dir[2], containerWidth, containerHeight);
      const end = project(axis.dir[0], axis.dir[1], axis.dir[2], containerWidth, containerHeight);
      ctx.beginPath();
      ctx.moveTo(start.sx, start.sy);
      ctx.lineTo(end.sx, end.sy);
      ctx.strokeStyle = axis.color;
      ctx.lineWidth = 0.5;
      ctx.globalAlpha = 0.3;
      ctx.stroke();
      ctx.globalAlpha = 1;

      // Axis label at the positive end
      ctx.font = "400 9px 'JetBrains Mono', monospace";
      ctx.fillStyle = "#64748B";
      ctx.textAlign = "center";
      ctx.fillText(axis.label, end.sx, end.sy - 6);
    }

    // Draw points
    for (const { point, sx, sy, depth } of projected) {
      if (sx < -10 || sx > containerWidth + 10 || sy < -10 || sy > containerHeight + 10) continue;

      // Size and opacity based on depth (closer = bigger/brighter)
      const depthNorm = (depth + 1.5) / 3; // roughly 0..1
      const radius = 2.5 + depthNorm * 2.5;
      const alpha = 0.3 + depthNorm * 0.5;

      ctx.beginPath();
      ctx.arc(sx, sy, radius, 0, Math.PI * 2);
      ctx.fillStyle = SOURCE_COLORS[point.source] || "#94A3B8";
      ctx.globalAlpha = alpha;
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
    ctx.textBaseline = "alphabetic";
    ctx.fillText(
      `${data.stats.projected} / ${data.stats.total_embeddings} points · 3D PCA`,
      8,
      containerHeight - 8,
    );
  }, [data, project]);

  // Animation loop for auto-rotation
  useEffect(() => {
    const tick = () => {
      if (autoRotateRef.current) {
        rotYRef.current += 0.003;
      }
      draw();
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [draw]);

  const findPoint = useCallback(
    (mx: number, my: number): EmbeddingProjectionPoint | null => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const hitRadius = 10;

      // Check front-to-back (reverse of draw order)
      let best: { point: EmbeddingProjectionPoint; dist: number } | null = null;
      for (const point of data.points) {
        const { sx, sy } = project(point.x, point.y, point.z, w, h);
        const dx = mx - sx;
        const dy = my - sy;
        const dist = dx * dx + dy * dy;
        if (dist < hitRadius * hitRadius) {
          if (!best || dist < best.dist) {
            best = { point, dist };
          }
        }
      }
      return best?.point ?? null;
    },
    [data, project],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (draggingRef.current) {
        const dx = mx - lastMouseRef.current.x;
        const dy = my - lastMouseRef.current.y;
        rotYRef.current -= dx * 0.008;
        rotXRef.current += dy * 0.008;
        // Clamp X rotation to avoid flipping
        rotXRef.current = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, rotXRef.current));
        lastMouseRef.current = { x: mx, y: my };
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
    [findPoint],
  );

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    draggingRef.current = true;
    autoRotateRef.current = false;
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
