"use client";

import { useEffect, useRef, useState } from "react";

const SOURCE_COLORS: Record<string, string> = {
  history: "#8B5CF6",
  notebook: "#22C55E",
  table: "#3B82F6",
};

type Point3D = {
  x: number;
  y: number;
  z: number;
  source: "history" | "notebook" | "table";
};

// Seeded cluster layout in [-1, 1]^3. Three clusters + a few bridge points,
// hand-placed so the rotating cloud reads as distinct colored blobs.
function buildPoints(): Point3D[] {
  const cluster = (
    cx: number,
    cy: number,
    cz: number,
    spread: number,
    count: number,
    source: Point3D["source"],
    seed: number,
  ): Point3D[] => {
    const out: Point3D[] = [];
    for (let i = 0; i < count; i++) {
      const a = Math.sin(seed + i * 12.9898) * 43758.5453;
      const b = Math.sin(seed + i * 78.233) * 12345.6789;
      const c = Math.sin(seed + i * 39.425) * 91234.5678;
      const rx = (a - Math.floor(a)) * 2 - 1;
      const ry = (b - Math.floor(b)) * 2 - 1;
      const rz = (c - Math.floor(c)) * 2 - 1;
      out.push({
        x: cx + rx * spread,
        y: cy + ry * spread,
        z: cz + rz * spread,
        source,
      });
    }
    return out;
  };

  return [
    ...cluster(-0.7, 0.35, -0.1, 0.32, 16, "history", 1.1),
    ...cluster(0.05, -0.05, 0.25, 0.38, 14, "notebook", 2.3),
    ...cluster(0.72, -0.5, 0.15, 0.24, 10, "table", 3.7),
    // bridges
    { x: -0.25, y: 0.15, z: 0.0, source: "history" },
    { x: 0.35, y: -0.25, z: 0.2, source: "notebook" },
    { x: 0.5, y: -0.4, z: 0.35, source: "table" },
  ];
}

const POINTS = buildPoints();

function rotate(
  x: number,
  y: number,
  z: number,
  rY: number,
  rX: number,
): [number, number, number] {
  const cY = Math.cos(rY);
  const sY = Math.sin(rY);
  const x1 = x * cY + z * sY;
  const z1 = -x * sY + z * cY;
  const cX = Math.cos(rX);
  const sX = Math.sin(rX);
  const y1 = y * cX - z1 * sX;
  const z2 = y * sX + z1 * cX;
  return [x1, y1, z2];
}

const WIDTH = 600;
const HEIGHT = 360;
const FOV = 3;
const BASE_SCALE = Math.min(WIDTH, HEIGHT) * 0.34;

type Projected = {
  cx: number;
  cy: number;
  r: number;
  opacity: number;
  color: string;
  depth: number;
};

function project(points: Point3D[], rotY: number, rotX: number): Projected[] {
  const out: Projected[] = points.map((p) => {
    const [rx, ry, rz] = rotate(p.x, p.y, p.z, rotY, rotX);
    const viewDist = FOV + rz;
    const scale = BASE_SCALE * (FOV / Math.max(viewDist, 0.5));
    const depth = (rz + 1) / 2; // 0 = far, 1 = near
    return {
      cx: WIDTH / 2 + rx * scale,
      cy: HEIGHT / 2 + ry * scale,
      r: 2.4 + depth * 3.6,
      opacity: 0.35 + depth * 0.6,
      color: SOURCE_COLORS[p.source],
      depth,
    };
  });
  out.sort((a, b) => a.depth - b.depth);
  return out;
}

export default function EmbeddingProjection3D() {
  const [projected, setProjected] = useState<Projected[]>([]);
  const rotYRef = useRef(0.4);
  const rotXRef = useRef(0.3);
  const rafRef = useRef<number | null>(null);
  const lastRef = useRef<number | null>(null);

  useEffect(() => {
    setProjected(project(POINTS, rotYRef.current, rotXRef.current));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;

    const tick = (t: number) => {
      if (lastRef.current == null) lastRef.current = t;
      const dt = (t - lastRef.current) / 1000;
      lastRef.current = t;
      rotYRef.current += dt * 0.35;
      rotXRef.current = 0.3 + Math.sin(t / 4200) * 0.12;
      setProjected(project(POINTS, rotYRef.current, rotXRef.current));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div
      className="relative overflow-hidden rounded-[14px] border border-border bg-background"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-[#8B5CF6]" />
          <span className="text-[13px] font-semibold text-ink">
            embedding projection
          </span>
          <span className="font-mono text-[11px] text-muted">
            memory_reading_store
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-dim">
          {POINTS.length} / 1,284 points
        </span>
      </div>
      <div className="relative aspect-[600/360] w-full">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="3D embedding projection, auto-rotating"
        >
          <defs>
            <pattern
              id="embed-grid"
              width="40"
              height="40"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 40 0 L 0 0 0 40"
                fill="none"
                stroke="rgba(15,23,42,0.04)"
                strokeWidth="1"
              />
            </pattern>
            <radialGradient id="embed-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(249,115,22,0.06)" />
              <stop offset="100%" stopColor="rgba(249,115,22,0)" />
            </radialGradient>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="url(#embed-grid)" />
          <rect width={WIDTH} height={HEIGHT} fill="url(#embed-glow)" />

          {projected.map((p, i) => (
            <circle
              key={i}
              cx={p.cx}
              cy={p.cy}
              r={p.r}
              fill={p.color}
              opacity={p.opacity}
            />
          ))}
        </svg>

        <div className="absolute bottom-3 left-3 flex flex-col gap-1 rounded-md border border-border-subtle bg-background/85 px-2.5 py-2 backdrop-blur">
          {[
            { src: "history", label: "History" },
            { src: "notebook", label: "Notebooks" },
            { src: "table", label: "Tables" },
          ].map((row) => (
            <div
              key={row.src}
              className="flex items-center gap-2 font-mono text-[10.5px] text-dim"
            >
              <span
                className="h-[7px] w-[7px] rounded-full"
                style={{ background: SOURCE_COLORS[row.src] }}
              />
              {row.label}
            </div>
          ))}
        </div>

        <div className="absolute bottom-3 right-3 rounded-md border border-border-subtle bg-background/85 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-dim backdrop-blur">
          auto-rotate
        </div>
      </div>
    </div>
  );
}
