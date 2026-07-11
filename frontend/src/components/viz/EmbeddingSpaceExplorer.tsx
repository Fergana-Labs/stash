"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingProjection, EmbeddingProjectionPoint } from "../../lib/types";

const SOURCE_COLORS: Record<string, [number, number, number]> = {
  history_events: [249, 115, 22], // orange — sessions
  pages: [34, 197, 94], // green — files
  table_rows: [59, 130, 246], // blue — tables
};
const FALLBACK_COLOR: [number, number, number] = [148, 163, 184];

interface TooltipInfo {
  x: number;
  y: number;
  point: EmbeddingProjectionPoint;
}

interface Props {
  data: EmbeddingProjection;
  onPointClick?: (point: EmbeddingProjectionPoint) => void;
}

// Rotate a 3D point around the Y axis, then X axis
function rotatePoint(
  px: number,
  py: number,
  pz: number,
  rotY: number,
  rotX: number,
): [number, number, number] {
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

/** Each point's 2 nearest neighbors in 3D — the constellation lines that turn
 *  a dot cloud into visible structure. O(n²) but computed once per dataset. */
function nearestNeighborEdges(points: EmbeddingProjectionPoint[]): [number, number][] {
  const edges = new Set<number>();
  const n = points.length;
  for (let i = 0; i < n; i++) {
    let best1 = -1, best2 = -1;
    let d1 = Infinity, d2 = Infinity;
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const dx = points[i].x - points[j].x;
      const dy = points[i].y - points[j].y;
      const dz = points[i].z - points[j].z;
      const d = dx * dx + dy * dy + dz * dz;
      if (d < d1) {
        d2 = d1; best2 = best1;
        d1 = d; best1 = j;
      } else if (d < d2) {
        d2 = d; best2 = j;
      }
    }
    for (const j of [best1, best2]) {
      if (j >= 0) edges.add(i < j ? i * n + j : j * n + i);
    }
  }
  return [...edges].map((key) => [Math.floor(key / n), key % n]);
}

export default function EmbeddingSpaceExplorer({ data, onPointClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  // Rotation state (radians)
  const rotYRef = useRef(0.4);
  const rotXRef = useRef(0.3);
  const draggingRef = useRef(false);
  const downPosRef = useRef<{ x: number; y: number } | null>(null);
  const movedRef = useRef(false);
  const lastMouseRef = useRef({ x: 0, y: 0 });
  const autoRotateRef = useRef(true);
  const animRef = useRef<number>(0);

  const edges = useMemo(() => nearestNeighborEdges(data.points), [data]);

  // Project a 3D point to 2D screen coordinates with perspective
  const project = useCallback(
    (px: number, py: number, pz: number, w: number, h: number) => {
      const [rx, ry, rz] = rotatePoint(px, py, pz, rotYRef.current, rotXRef.current);

      const fov = 3;
      const viewDist = fov + rz;
      const scale = Math.min(w, h) * 0.42 * (fov / Math.max(viewDist, 0.5));

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
    const containerHeight = canvas.parentElement?.clientHeight || 320;
    const dpr = window.devicePixelRatio || 2;

    canvas.width = containerWidth * dpr;
    canvas.height = containerHeight * dpr;
    canvas.style.width = `${containerWidth}px`;
    canvas.style.height = `${containerHeight}px`;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, containerWidth, containerHeight);

    const projected = data.points.map((point) => {
      const { sx, sy, depth } = project(point.x, point.y, point.z, containerWidth, containerHeight);
      return { point, sx, sy, depth };
    });

    // Constellation lines first, faded by the depth of their midpoint.
    for (const [a, b] of edges) {
      const pa = projected[a];
      const pb = projected[b];
      const depthNorm = Math.max(0, Math.min(1, ((pa.depth + pb.depth) / 2 + 1.5) / 3));
      ctx.beginPath();
      ctx.moveTo(pa.sx, pa.sy);
      ctx.lineTo(pb.sx, pb.sy);
      ctx.strokeStyle = `rgba(26,23,20,${0.05 + depthNorm * 0.12})`;
      ctx.lineWidth = 0.75;
      ctx.stroke();
    }

    // Points back-to-front for correct overlap; halo pass + core pass per
    // point gives a soft glow without the cost of shadowBlur.
    projected.sort((a, b) => a.depth - b.depth);
    for (const { point, sx, sy, depth } of projected) {
      if (sx < -20 || sx > containerWidth + 20 || sy < -20 || sy > containerHeight + 20) continue;

      const depthNorm = Math.max(0, Math.min(1, (depth + 1.5) / 3)); // 0 far, 1 near
      const [r, g, b] = SOURCE_COLORS[point.source] || FALLBACK_COLOR;
      const radius = 1.6 + depthNorm * 2.6;

      ctx.beginPath();
      ctx.arc(sx, sy, radius * 2.6, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r},${g},${b},${0.05 + depthNorm * 0.12})`;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(sx, sy, radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r},${g},${b},${0.35 + depthNorm * 0.6})`;
      ctx.fill();
    }
  }, [data, edges, project]);

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
        // Mark as a drag (not a click) once the cursor moves past a small threshold
        if (downPosRef.current) {
          const totalDx = mx - downPosRef.current.x;
          const totalDy = my - downPosRef.current.y;
          if (totalDx * totalDx + totalDy * totalDy > 16) movedRef.current = true;
        }
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
    const pos = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    lastMouseRef.current = pos;
    downPosRef.current = pos;
    movedRef.current = false;
  }, []);

  const handleMouseUp = useCallback(() => {
    draggingRef.current = false;
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if (!onPointClick) return;
      if (movedRef.current) return; // it was a drag, not a click
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const point = findPoint(e.clientX - rect.left, e.clientY - rect.top);
      if (point) onPointClick(point);
    },
    [findPoint, onPointClick],
  );

  return (
    <div className="relative h-full">
      <canvas
        ref={canvasRef}
        className="block w-full cursor-grab active:cursor-grabbing"
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
        </div>
      )}
    </div>
  );
}
