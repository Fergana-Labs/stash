"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { WikiGraph as WikiGraphData, WikiGraphNode } from "@/lib/api";

const HEIGHT = 560;
const MIN_SCALE = 0.25;
const MAX_SCALE = 4;

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
  // Bigger graphs need more shove to claim the same canvas.
  const repulsion = 15000 * Math.max(1, n / 25);

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = x[i] - x[j];
      const dy = y[i] - y[j];
      const d2 = Math.max(dx * dx + dy * dy, 400);
      const f = (repulsion * alpha) / d2;
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

interface View {
  scale: number;
  tx: number;
  ty: number;
}

type Drag =
  | { mode: "pan"; lastX: number; lastY: number; moved: boolean }
  | { mode: "node"; index: number; moved: boolean; wx: number; wy: number };

/** Obsidian-style force graph of the Memory wiki — pages as nodes sized and
 *  colored by link count, page-to-page links as edges. Scroll to zoom, drag
 *  the canvas to pan, drag a node to rearrange (the layout re-settles around
 *  it), double-click to reset the view, click a node to open its page. */
export default function WikiGraph({ data }: { data: WikiGraphData }) {
  const router = useRouter();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simRef = useRef<Sim | null>(null);
  const viewRef = useRef<View>({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<Drag | null>(null);
  const hoverRef = useRef<number>(-1);
  // Until the user zooms/pans/drags, the view auto-fits the whole graph
  // (the settling layout grows past the canvas otherwise). Double-click
  // hands control back to the auto-fit.
  const userAdjustedRef = useRef(false);
  const [cursor, setCursor] = useState("grab");

  const toWorld = useCallback((mx: number, my: number) => {
    const v = viewRef.current;
    return { wx: (mx - v.tx) / v.scale, wy: (my - v.ty) / v.scale };
  }, []);

  const findNode = useCallback((wx: number, wy: number): number => {
    const sim = simRef.current;
    if (!sim) return -1;
    for (let i = 0; i < sim.nodes.length; i++) {
      const dx = wx - sim.x[i];
      const dy = wy - sim.y[i];
      const r = nodeRadius(sim.nodes[i].degree) + 4;
      if (dx * dx + dy * dy <= r * r) return i;
    }
    return -1;
  }, []);

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

    const v = viewRef.current;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, HEIGHT);
    ctx.translate(v.tx, v.ty);
    ctx.scale(v.scale, v.scale);

    // Faint 40px grid over the visible world rect, so panning reads as motion.
    const wx0 = -v.tx / v.scale;
    const wy0 = -v.ty / v.scale;
    const wx1 = (w - v.tx) / v.scale;
    const wy1 = (HEIGHT - v.ty) / v.scale;
    ctx.strokeStyle = "rgba(26,23,20,0.04)";
    ctx.lineWidth = 1 / v.scale;
    for (let gx = Math.floor(wx0 / 40) * 40; gx <= wx1; gx += 40) {
      ctx.beginPath();
      ctx.moveTo(gx, wy0);
      ctx.lineTo(gx, wy1);
      ctx.stroke();
    }
    for (let gy = Math.floor(wy0 / 40) * 40; gy <= wy1; gy += 40) {
      ctx.beginPath();
      ctx.moveTo(wx0, gy);
      ctx.lineTo(wx1, gy);
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
      ctx.lineWidth = (active ? 1.5 : 1) / Math.sqrt(v.scale);
      ctx.stroke();
    }

    // At overview zoom only hubs (and the hovered node) get labels — the
    // fit-scale core is too dense for full text. Zooming in labels every
    // node, earlier for small wikis. Label screen size shrinks a little
    // zoomed out and caps zoomed in, so text never drowns the nodes.
    const labelAll = v.scale >= (nodes.length <= 40 ? 0.8 : 1.5);
    const labelPx = Math.min(12, Math.max(8.5, 11 * v.scale));
    ctx.font = `${labelPx / v.scale}px ui-monospace, Menlo, monospace`;
    ctx.textBaseline = "middle";
    const labelPad = 5 / v.scale;
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
        const left = x[i] > wx1 - 130 / v.scale;
        ctx.fillStyle = i === hover ? "rgba(26,23,20,0.92)" : "rgba(26,23,20,0.62)";
        ctx.textAlign = left ? "right" : "left";
        ctx.fillText(label, left ? x[i] - r - labelPad : x[i] + r + labelPad, y[i]);
      }
      ctx.globalAlpha = 1;
    }
  }, []);

  useEffect(() => {
    const w = canvasRef.current?.parentElement?.clientWidth || 600;
    const sim = buildSim(data, w, HEIGHT);
    simRef.current = sim;
    viewRef.current = { scale: 1, tx: 0, ty: 0 };
    // Obsidian-style fit: frame the 5th–95th percentile of node positions
    // with tight margins, so a stray leaf sits near the edge instead of
    // shrinking the whole map to include it.
    const fitView = () => {
      const xs = Array.from(sim.x).sort((a, b) => a - b);
      const ys = Array.from(sim.y).sort((a, b) => a - b);
      const k = Math.floor(xs.length * 0.05);
      const minX = xs[k], maxX = xs[xs.length - 1 - k];
      const minY = ys[k], maxY = ys[ys.length - 1 - k];
      const bw = Math.max(maxX - minX, 1);
      const bh = Math.max(maxY - minY, 1);
      const padX = 60, padY = 30;
      const scale = Math.min((w - 2 * padX) / bw, (HEIGHT - 2 * padY) / bh, 1);
      const v = viewRef.current;
      v.scale = scale;
      v.tx = (w - bw * scale) / 2 - minX * scale;
      v.ty = (HEIGHT - bh * scale) / 2 - minY * scale;
    };

    let raf = 0;
    const step = () => {
      if (sim.alpha > 0.02) tick(sim, w, HEIGHT);
      if (!userAdjustedRef.current) fitView();
      // A held node stays glued to the cursor — the tick above would
      // otherwise spring it back toward its neighbors every frame.
      const drag = dragRef.current;
      if (drag?.mode === "node") {
        sim.x[drag.index] = drag.wx;
        sim.y[drag.index] = drag.wy;
        sim.vx[drag.index] = 0;
        sim.vy[drag.index] = 0;
      }
      draw();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [data, draw]);

  // React registers onWheel passively, so preventDefault (needed to stop the
  // page scrolling while zooming) requires a native non-passive listener.
  // Plain wheel scrolls the page — the graph sits mid-page, so swallowing
  // every wheel event traps scrolling whenever the cursor crosses it. Zoom
  // needs ⌘/ctrl held; trackpad pinch arrives as ctrl+wheel, so it zooms too.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.metaKey && !e.ctrlKey) return;
      e.preventDefault();
      userAdjustedRef.current = true;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const v = viewRef.current;
      const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * Math.exp(-e.deltaY * 0.0015)));
      // Zoom anchored on the cursor: the world point under it stays put.
      v.tx = mx - ((mx - v.tx) / v.scale) * next;
      v.ty = my - ((my - v.ty) / v.scale) * next;
      v.scale = next;
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className="w-full"
        style={{ height: HEIGHT, cursor }}
        onMouseDown={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          const { wx, wy } = toWorld(mx, my);
          const i = findNode(wx, wy);
          dragRef.current =
            i >= 0
              ? { mode: "node", index: i, moved: false, wx, wy }
              : { mode: "pan", lastX: mx, lastY: my, moved: false };
          if (i < 0) setCursor("grabbing");
        }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          const drag = dragRef.current;
          const sim = simRef.current;

          if (drag?.mode === "pan") {
            userAdjustedRef.current = true;
            viewRef.current.tx += mx - drag.lastX;
            viewRef.current.ty += my - drag.lastY;
            if (Math.abs(mx - drag.lastX) + Math.abs(my - drag.lastY) > 2) drag.moved = true;
            drag.lastX = mx;
            drag.lastY = my;
            return;
          }
          if (drag?.mode === "node" && sim) {
            // Freeze auto-fit — refitting mid-drag would slide the world
            // under the cursor.
            userAdjustedRef.current = true;
            const { wx, wy } = toWorld(mx, my);
            drag.wx = wx;
            drag.wy = wy;
            // Re-warm so neighbors re-settle around the dragged node.
            sim.alpha = Math.max(sim.alpha, 0.25);
            drag.moved = true;
            return;
          }

          const { wx, wy } = toWorld(mx, my);
          const i = findNode(wx, wy);
          hoverRef.current = i;
          setCursor(i >= 0 ? "pointer" : "grab");
        }}
        onMouseUp={() => {
          const drag = dragRef.current;
          if (drag?.mode === "pan") setCursor("grab");
          // The click handler (which fires synchronously after mouseup) still
          // needs `moved` to suppress navigation — clear on the next task.
          setTimeout(() => {
            if (dragRef.current === drag) dragRef.current = null;
          }, 0);
        }}
        onMouseLeave={() => {
          dragRef.current = null;
          hoverRef.current = -1;
          setCursor("grab");
        }}
        onClick={(e) => {
          const drag = dragRef.current;
          dragRef.current = null;
          if (drag?.moved) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const { wx, wy } = toWorld(e.clientX - rect.left, e.clientY - rect.top);
          const i = findNode(wx, wy);
          const sim = simRef.current;
          if (i >= 0 && sim) router.push(`/p/${sim.nodes[i].id}?section=memory`);
        }}
        onDoubleClick={() => {
          userAdjustedRef.current = false;
        }}
      />
      <div className="absolute bottom-2 left-2 rounded-md border border-border bg-base/85 px-2.5 py-1.5 font-mono text-[10.5px] text-muted-foreground backdrop-blur">
        ⌘ scroll to zoom · drag to pan · double-click to fit
      </div>
    </div>
  );
}
