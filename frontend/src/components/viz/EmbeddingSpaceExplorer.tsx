"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EmbeddingProjection, EmbeddingProjectionPoint } from "../../lib/types";

// One hue per semantic island (k-means cluster of the 3D UMAP coords).
const CLUSTER_COLORS: [number, number, number][] = [
  [249, 115, 22], // orange
  [59, 130, 246], // blue
  [34, 197, 94], // green
  [139, 92, 246], // violet
  [245, 158, 11], // amber
  [20, 184, 166], // teal
  [244, 63, 94], // rose
  [100, 116, 139], // slate
];

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

interface Prep {
  /** Coordinates rescaled so the cloud fills the unit sphere. */
  coords: [number, number, number][];
  /** Cluster index per point. */
  cluster: number[];
  /** Per cluster, the index of the point closest to its centroid — its label. */
  representatives: number[];
}

/** Normalize the cloud to fill the view and split it into semantic islands
 *  (plain k-means on the 3D coords — they're already neighbor-preserving).
 *  Deterministic: centroids seed from evenly-strided points. */
function prepare(points: EmbeddingProjectionPoint[]): Prep {
  const n = points.length;
  // Fill the view from the 90th-percentile radius, not the max — otherwise
  // one far outlier shrinks the whole cloud (it just renders past the edge).
  const radii = points.map((p) => Math.hypot(p.x, p.y, p.z)).sort((a, b) => a - b);
  const fitR = radii[Math.min(n - 1, Math.floor(n * 0.9))];
  const s = fitR > 0 ? 1 / fitR : 1;
  const coords = points.map((p) => [p.x * s, p.y * s, p.z * s] as [number, number, number]);

  const k = Math.max(1, Math.min(CLUSTER_COLORS.length, Math.round(Math.sqrt(n / 2))));
  const centroids = Array.from({ length: k }, (_, c) => [...coords[Math.floor((c * n) / k)]]);
  const cluster = new Array<number>(n).fill(0);

  for (let iter = 0; iter < 12; iter++) {
    for (let i = 0; i < n; i++) {
      let best = 0;
      let bestD = Infinity;
      for (let c = 0; c < k; c++) {
        const dx = coords[i][0] - centroids[c][0];
        const dy = coords[i][1] - centroids[c][1];
        const dz = coords[i][2] - centroids[c][2];
        const d = dx * dx + dy * dy + dz * dz;
        if (d < bestD) {
          bestD = d;
          best = c;
        }
      }
      cluster[i] = best;
    }
    const sums = Array.from({ length: k }, () => [0, 0, 0, 0]);
    for (let i = 0; i < n; i++) {
      const sum = sums[cluster[i]];
      sum[0] += coords[i][0];
      sum[1] += coords[i][1];
      sum[2] += coords[i][2];
      sum[3] += 1;
    }
    for (let c = 0; c < k; c++) {
      if (sums[c][3] > 0) {
        centroids[c] = [sums[c][0] / sums[c][3], sums[c][1] / sums[c][3], sums[c][2] / sums[c][3]];
      }
    }
  }

  const representatives: number[] = [];
  for (let c = 0; c < k; c++) {
    let best = -1;
    let bestD = Infinity;
    for (let i = 0; i < n; i++) {
      if (cluster[i] !== c) continue;
      const dx = coords[i][0] - centroids[c][0];
      const dy = coords[i][1] - centroids[c][1];
      const dz = coords[i][2] - centroids[c][2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best >= 0) representatives.push(best);
  }

  return { coords, cluster, representatives };
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

  const prep = useMemo(() => prepare(data.points), [data]);

  // Project a 3D point to 2D screen coordinates with perspective
  const project = useCallback(
    (px: number, py: number, pz: number, w: number, h: number) => {
      const [rx, ry, rz] = rotatePoint(px, py, pz, rotYRef.current, rotXRef.current);

      const fov = 3;
      const viewDist = fov + rz;
      const scale = Math.min(w, h) * 0.52 * (fov / Math.max(viewDist, 0.5));

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

    const { coords, cluster, representatives } = prep;
    const projected = coords.map(([x, y, z]) => project(x, y, z, containerWidth, containerHeight));

    // Points back-to-front for correct overlap; halo pass + core pass per
    // point gives a soft glow without the cost of shadowBlur.
    const order = projected.map((_, i) => i).sort((a, b) => projected[a].depth - projected[b].depth);
    for (const i of order) {
      const { sx, sy, depth } = projected[i];
      if (sx < -20 || sx > containerWidth + 20 || sy < -20 || sy > containerHeight + 20) continue;

      const depthNorm = Math.max(0, Math.min(1, (depth + 1) / 2)); // 0 far, 1 near
      const [r, g, b] = CLUSTER_COLORS[cluster[i] % CLUSTER_COLORS.length];
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

    // One label per island: the page closest to the cluster centroid, so
    // each blob of color says what it's about.
    ctx.font = "10.5px ui-monospace, Menlo, monospace";
    ctx.textBaseline = "middle";
    for (const i of representatives) {
      const { sx, sy, depth } = projected[i];
      const depthNorm = Math.max(0, Math.min(1, (depth + 1) / 2));
      const name = data.points[i].label;
      const label = name.length > 24 ? `${name.slice(0, 23)}…` : name;
      // Flip to the left side near the right edge so labels never clip.
      const left = sx > containerWidth - 150;
      ctx.textAlign = left ? "right" : "left";
      const lx = left ? sx - 7 : sx + 7;
      // Halo so the label survives crossing other points.
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(255,255,255,0.85)";
      ctx.strokeText(label, lx, sy);
      ctx.fillStyle = `rgba(26,23,20,${0.4 + depthNorm * 0.5})`;
      ctx.fillText(label, lx, sy);
    }
  }, [data, prep, project]);

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

      let best: { point: EmbeddingProjectionPoint; dist: number } | null = null;
      for (let i = 0; i < prep.coords.length; i++) {
        const [x, y, z] = prep.coords[i];
        const { sx, sy } = project(x, y, z, w, h);
        const dx = mx - sx;
        const dy = my - sy;
        const dist = dx * dx + dy * dy;
        if (dist < hitRadius * hitRadius) {
          if (!best || dist < best.dist) {
            best = { point: data.points[i], dist };
          }
        }
      }
      return best?.point ?? null;
    },
    [data, prep, project],
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
