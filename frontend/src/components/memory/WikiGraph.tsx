"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { WikiGraph as WikiGraphData, WikiGraphNode } from "@/lib/api";

const HEIGHT = 360;

// Landing-page "Wiki" card palette: orange hubs, warm-gray leaves.
function nodeColor(degree: number): string {
  if (degree >= 5) return "#F97316";
  if (degree >= 3) return "#EA7C1F";
  if (degree === 0) return "#F97316";
  return "#6B655B";
}

function nodeRadius(degree: number): number {
  return Math.min(6 + degree * 1.2, 15);
}

interface Sim {
  nodes: WikiGraphNode[];
  x: Float64Array;
  y: Float64Array;
  vx: Float64Array;
  vy: Float64Array;
  edges: [number, number][];
  alpha: number;
}

function buildSim(data: WikiGraphData, w: number, h: number): Sim {
  const n = data.nodes.length;
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  // Seed on a golden-angle spiral so the simulation starts untangled and
  // deterministic (same graph → same layout).
  for (let i = 0; i < n; i++) {
    const angle = i * 2.399963;
    const r = 24 + 13 * Math.sqrt(i);
    x[i] = w / 2 + r * Math.cos(angle);
    y[i] = h / 2 + r * Math.sin(angle);
  }
  const index = new Map(data.nodes.map((node, i) => [node.id, i]));
  const edges = data.edges.map(
    (e) => [index.get(e.source)!, index.get(e.target)!] as [number, number],
  );
  return { nodes: data.nodes, x, y, vx: new Float64Array(n), vy: new Float64Array(n), edges, alpha: 1 };
}

/** One force-layout step: node-pair repulsion, edge springs, center gravity. */
function tick(sim: Sim, w: number, h: number) {
  const { x, y, vx, vy, edges, alpha } = sim;
  const n = x.length;

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = x[i] - x[j];
      const dy = y[i] - y[j];
      const d2 = Math.max(dx * dx + dy * dy, 400);
      const f = (15000 * alpha) / d2;
      const d = Math.sqrt(d2);
      vx[i] += (dx / d) * f;
      vy[i] += (dy / d) * f;
      vx[j] -= (dx / d) * f;
      vy[j] -= (dy / d) * f;
    }
  }

  for (const [a, b] of edges) {
    const dx = x[b] - x[a];
    const dy = y[b] - y[a];
    const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
    const f = (d - 110) * 0.05 * alpha;
    vx[a] += (dx / d) * f;
    vy[a] += (dy / d) * f;
    vx[b] -= (dx / d) * f;
    vy[b] -= (dy / d) * f;
  }

  for (let i = 0; i < n; i++) {
    vx[i] += (w / 2 - x[i]) * 0.006 * alpha;
    vy[i] += (h / 2 - y[i]) * 0.006 * alpha;
    vx[i] *= 0.82;
    vy[i] *= 0.82;
    x[i] += vx[i];
    y[i] += vy[i];
  }

  sim.alpha *= 0.985;
}

/** Obsidian-style force graph of the Memory wiki — pages as nodes sized and
 *  colored by link count, page-to-page links as edges. Click a node to open
 *  that page; the layout settles live on load. */
export default function WikiGraph({ data }: { data: WikiGraphData }) {
  const router = useRouter();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<Sim | null>(null);
  const hoverRef = useRef<number>(-1);
  const [hovered, setHovered] = useState<number>(-1);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const sim = simRef.current;
    if (!canvas || !sim) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = canvas.parentElement?.clientWidth || 600;
    const dpr = window.devicePixelRatio || 2;
    canvas.width = w * dpr;
    canvas.height = HEIGHT * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${HEIGHT}px`;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, HEIGHT);

    // Faint 40px grid, matching the landing card's backdrop.
    ctx.strokeStyle = "rgba(26,23,20,0.04)";
    ctx.lineWidth = 1;
    for (let gx = 0; gx <= w; gx += 40) {
      ctx.beginPath();
      ctx.moveTo(gx, 0);
      ctx.lineTo(gx, HEIGHT);
      ctx.stroke();
    }
    for (let gy = 0; gy <= HEIGHT; gy += 40) {
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(w, gy);
      ctx.stroke();
    }

    const { nodes, x, y, edges } = sim;
    const hover = hoverRef.current;
    const neighbors = new Set<number>();
    if (hover >= 0) {
      for (const [a, b] of edges) {
        if (a === hover) neighbors.add(b);
        if (b === hover) neighbors.add(a);
      }
    }

    for (const [a, b] of edges) {
      const active = hover >= 0 && (a === hover || b === hover);
      ctx.beginPath();
      ctx.moveTo(x[a], y[a]);
      ctx.lineTo(x[b], y[b]);
      ctx.strokeStyle = active ? "rgba(249,115,22,0.55)" : "rgba(26,23,20,0.22)";
      ctx.lineWidth = active ? 1.5 : 1;
      ctx.stroke();
    }

    // Label everything on small wikis; only hubs + the hovered node on big ones.
    const labelAll = nodes.length <= 40;
    ctx.font = "11px ui-monospace, Menlo, monospace";
    ctx.textBaseline = "middle";
    for (let i = 0; i < nodes.length; i++) {
      const r = nodeRadius(nodes[i].degree);
      ctx.beginPath();
      ctx.arc(x[i], y[i], r, 0, Math.PI * 2);
      ctx.fillStyle = nodeColor(nodes[i].degree);
      ctx.globalAlpha = hover >= 0 && i !== hover && !neighbors.has(i) ? 0.35 : 1;
      ctx.fill();
      ctx.strokeStyle = "white";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      if (labelAll || nodes[i].degree >= 3 || i === hover) {
        const label =
          nodes[i].name.length > 26 ? `${nodes[i].name.slice(0, 25)}…` : nodes[i].name;
        const left = x[i] > w - 130;
        ctx.fillStyle = i === hover ? "rgba(26,23,20,0.92)" : "rgba(26,23,20,0.62)";
        ctx.textAlign = left ? "right" : "left";
        ctx.fillText(label, left ? x[i] - r - 5 : x[i] + r + 5, y[i]);
      }
      ctx.globalAlpha = 1;
    }
  }, []);

  useEffect(() => {
    const w = canvasRef.current?.parentElement?.clientWidth || 600;
    const sim = buildSim(data, w, HEIGHT);
    simRef.current = sim;
    let raf = 0;
    const step = () => {
      if (sim.alpha > 0.02) tick(sim, w, HEIGHT);
      draw();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [data, draw]);

  const findNode = useCallback((mx: number, my: number): number => {
    const sim = simRef.current;
    if (!sim) return -1;
    for (let i = 0; i < sim.nodes.length; i++) {
      const dx = mx - sim.x[i];
      const dy = my - sim.y[i];
      const r = nodeRadius(sim.nodes[i].degree) + 4;
      if (dx * dx + dy * dy <= r * r) return i;
    }
    return -1;
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="w-full"
        style={{ height: HEIGHT, cursor: hovered >= 0 ? "pointer" : "default" }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const i = findNode(e.clientX - rect.left, e.clientY - rect.top);
          hoverRef.current = i;
          setHovered(i);
        }}
        onMouseLeave={() => {
          hoverRef.current = -1;
          setHovered(-1);
        }}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const i = findNode(e.clientX - rect.left, e.clientY - rect.top);
          const sim = simRef.current;
          if (i >= 0 && sim) router.push(`/p/${sim.nodes[i].id}?section=memory`);
        }}
      />
      <div className="absolute bottom-2 right-2 flex flex-col gap-1 rounded-md border border-border bg-base/85 px-2.5 py-2 backdrop-blur">
        {[
          { dot: "#F97316", label: "hub" },
          { dot: "#6B655B", label: "leaf" },
        ].map((row) => (
          <div key={row.label} className="flex items-center gap-2 font-mono text-[10.5px] text-muted-foreground">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: row.dot }} />
            {row.label}
          </div>
        ))}
      </div>
    </div>
  );
}
