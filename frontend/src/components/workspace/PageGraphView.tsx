"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { drag as d3drag, type D3DragEvent } from "d3-drag";
import { select } from "d3-selection";
import { zoom as d3zoom, zoomIdentity, type D3ZoomEvent, type ZoomTransform } from "d3-zoom";
import { useEffect, useRef, useState } from "react";
import type { PageGraph } from "../../lib/types";

interface PageGraphViewProps {
  graph: PageGraph;
  onClose: () => void;
  onSelectPage?: (pageId: string) => void;
  inline?: boolean;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  name: string;
  degree: number;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  source: string | SimNode;
  target: string | SimNode;
}

interface TooltipInfo {
  x: number;
  y: number;
  name: string;
}

const nodeRadius = (d: SimNode) => Math.min(12, 4 + d.degree);

export default function PageGraphView({ graph, onClose, onSelectPage, inline }: PageGraphViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);
  const [overNode, setOverNode] = useState(false);
  const clickable = Boolean(onSelectPage);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const dw = canvas.offsetWidth;
    const dh = canvas.offsetHeight;
    canvas.width = dw * dpr;
    canvas.height = dh * dpr;

    const degrees = new Map<string, number>();
    for (const e of graph.edges) {
      degrees.set(e.source, (degrees.get(e.source) || 0) + 1);
      degrees.set(e.target, (degrees.get(e.target) || 0) + 1);
    }

    const nodes: SimNode[] = graph.nodes.map((n) => ({
      id: n.id,
      name: n.name,
      degree: degrees.get(n.id) || 0,
      x: dw / 2 + (Math.random() - 0.5) * 30,
      y: dh / 2 + (Math.random() - 0.5) * 30,
    }));
    const nodeById = new Map(nodes.map((n) => [n.id, n]));

    const links: SimLink[] = graph.edges
      .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
      .map((e) => ({ source: e.source, target: e.target }));

    let hoveredId: string | null = null;
    let transform: ZoomTransform = zoomIdentity;

    const simulation: Simulation<SimNode, SimLink> = forceSimulation(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(80)
          .strength(0.4),
      )
      .force("charge", forceManyBody<SimNode>().strength(-400))
      .force("center", forceCenter(dw / 2, dh / 2))
      .force("x", forceX<SimNode>(dw / 2).strength(0.05))
      .force("y", forceY<SimNode>(dh / 2).strength(0.05))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d) => nodeRadius(d) + 4),
      )
      .alpha(1)
      .alphaDecay(0.0228)
      .velocityDecay(0.4);

    const findNode = (px: number, py: number): SimNode | null => {
      const [x, y] = transform.invert([px, py]);
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        const dx = (n.x ?? 0) - x;
        const dy = (n.y ?? 0) - y;
        const r = nodeRadius(n) + 4;
        if (dx * dx + dy * dy < r * r) return n;
      }
      return null;
    };

    const drawArrow = (tipX: number, tipY: number, angle: number, alpha: number) => {
      ctx.globalAlpha = alpha;
      const len = 6;
      ctx.beginPath();
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - len * Math.cos(angle - 0.4), tipY - len * Math.sin(angle - 0.4));
      ctx.moveTo(tipX, tipY);
      ctx.lineTo(tipX - len * Math.cos(angle + 0.4), tipY - len * Math.sin(angle + 0.4));
      ctx.stroke();
    };

    const connectedIds = (id: string): Set<string> => {
      const set = new Set<string>([id]);
      for (const l of links) {
        const s = (l.source as SimNode).id;
        const t = (l.target as SimNode).id;
        if (s === id) set.add(t);
        else if (t === id) set.add(s);
      }
      return set;
    };

    const draw = () => {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.scale(dpr, dpr);
      ctx.translate(transform.x, transform.y);
      ctx.scale(transform.k, transform.k);

      const lit = hoveredId ? connectedIds(hoveredId) : null;

      // Edges — detect bidirectional pairs once
      const bidir = new Set<string>();
      const drawn = new Set<string>();
      for (const l of links) {
        const s = (l.source as SimNode).id;
        const t = (l.target as SimNode).id;
        const rev = links.find(
          (o) => (o.source as SimNode).id === t && (o.target as SimNode).id === s,
        );
        if (rev) {
          bidir.add(s + ":" + t);
          bidir.add(t + ":" + s);
        }
      }

      ctx.strokeStyle = "#3E4E63";
      ctx.lineWidth = 1.2;
      for (const l of links) {
        const s = l.source as SimNode;
        const t = l.target as SimNode;
        const key = s.id + ":" + t.id;
        const isBidir = bidir.has(key);
        if (isBidir) {
          const canonKey = [s.id, t.id].sort().join(":");
          if (drawn.has(canonKey)) continue;
          drawn.add(canonKey);
        }
        const connected = !lit || (lit.has(s.id) && lit.has(t.id));
        const alpha = connected ? 1 : 0.08;
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.moveTo(s.x ?? 0, s.y ?? 0);
        ctx.lineTo(t.x ?? 0, t.y ?? 0);
        ctx.stroke();

        const angle = Math.atan2((t.y ?? 0) - (s.y ?? 0), (t.x ?? 0) - (s.x ?? 0));
        if (isBidir) {
          const rt = nodeRadius(t);
          const rs = nodeRadius(s);
          const tipTX = (t.x ?? 0) - Math.cos(angle) * rt;
          const tipTY = (t.y ?? 0) - Math.sin(angle) * rt;
          drawArrow(tipTX, tipTY, angle, alpha);
          const tipSX = (s.x ?? 0) + Math.cos(angle) * rs;
          const tipSY = (s.y ?? 0) + Math.sin(angle) * rs;
          drawArrow(tipSX, tipSY, angle + Math.PI, alpha);
        } else {
          const rt = nodeRadius(t);
          const tipX = (t.x ?? 0) - Math.cos(angle) * rt;
          const tipY = (t.y ?? 0) - Math.sin(angle) * rt;
          drawArrow(tipX, tipY, angle, alpha);
        }
      }

      // Nodes
      for (const n of nodes) {
        const isHovered = n.id === hoveredId;
        const connected = !lit || lit.has(n.id);
        ctx.globalAlpha = connected ? 1 : 0.15;
        ctx.beginPath();
        const r = isHovered ? nodeRadius(n) + 2 : nodeRadius(n);
        ctx.arc(n.x ?? 0, n.y ?? 0, r, 0, Math.PI * 2);
        ctx.fillStyle = isHovered ? "#EA580C" : n.degree > 0 ? "#F97316" : "#8B5CF6";
        ctx.fill();
      }

      // Labels — only when zoomed in enough, or always for the hovered set
      if (transform.k > 1.2 || lit) {
        ctx.fillStyle = "#9CA3AF";
        ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        for (const n of nodes) {
          if (lit && !lit.has(n.id)) continue;
          if (!lit && transform.k <= 1.2) continue;
          ctx.globalAlpha = 1;
          ctx.fillText(n.name, (n.x ?? 0) + nodeRadius(n) + 4, n.y ?? 0);
        }
      }

      ctx.globalAlpha = 1;
      ctx.restore();
    };

    simulation.on("tick", draw);

    const sel = select(canvas);

    const zoomBehavior = d3zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.2, 4])
      .filter((event) => {
        if (event.type === "wheel") return !event.ctrlKey;
        if (event.type === "mousedown") {
          const rect = canvas.getBoundingClientRect();
          return !findNode(event.clientX - rect.left, event.clientY - rect.top);
        }
        return !event.ctrlKey && !event.button;
      })
      .on("zoom", (event: D3ZoomEvent<HTMLCanvasElement, unknown>) => {
        transform = event.transform;
        draw();
      });

    sel.call(zoomBehavior);

    const dragBehavior = d3drag<HTMLCanvasElement, unknown>()
      .subject((event) => {
        const rect = canvas.getBoundingClientRect();
        return findNode(event.sourceEvent.clientX - rect.left, event.sourceEvent.clientY - rect.top);
      })
      .on("start", (event: D3DragEvent<HTMLCanvasElement, unknown, SimNode>) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        const [x, y] = transform.invert([event.x, event.y]);
        event.subject.fx = x;
        event.subject.fy = y;
      })
      .on("drag", (event: D3DragEvent<HTMLCanvasElement, unknown, SimNode>) => {
        const [x, y] = transform.invert([event.x, event.y]);
        event.subject.fx = x;
        event.subject.fy = y;
      })
      .on("end", (event: D3DragEvent<HTMLCanvasElement, unknown, SimNode>) => {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
      });

    sel.call(dragBehavior);

    const onMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const found = findNode(mx, my);
      hoveredId = found?.id ?? null;
      setOverNode(!!found);
      if (found) setTooltip({ x: mx, y: my, name: found.name });
      else setTooltip(null);
      draw();
    };

    const onLeave = () => {
      hoveredId = null;
      setOverNode(false);
      setTooltip(null);
      draw();
    };

    const onClick = (e: MouseEvent) => {
      if (!onSelectPage) return;
      const rect = canvas.getBoundingClientRect();
      const found = findNode(e.clientX - rect.left, e.clientY - rect.top);
      if (found) onSelectPage(found.id);
    };

    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseleave", onLeave);
    canvas.addEventListener("click", onClick);

    return () => {
      simulation.stop();
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mouseleave", onLeave);
      canvas.removeEventListener("click", onClick);
      sel.on(".zoom", null).on(".drag", null);
    };
  }, [graph, onSelectPage]);

  const tooltipEl = tooltip && (
    <div
      className="absolute z-10 bg-base border border-border rounded-md px-3 py-1.5 pointer-events-none shadow-lg"
      style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
    >
      <div className="text-xs font-medium text-brand underline underline-offset-2">{tooltip.name}</div>
      {clickable && <div className="text-[10px] text-muted mt-0.5">Click to open &#x2197;</div>}
    </div>
  );

  const cursorClass = clickable && overNode ? "cursor-pointer" : "cursor-grab";

  if (inline) {
    return (
      <div ref={containerRef} className="relative">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs text-muted">
            {graph.nodes.length} pages, {graph.edges.length} links
          </span>
          <span className="text-[10px] text-muted">drag to pan &middot; scroll to zoom</span>
        </div>
        <canvas
          ref={canvasRef}
          className={`w-full ${cursorClass} rounded`}
          style={{ height: 320 }}
        />
        {tooltipEl}
        {graph.edges.length === 0 && (
          <p className="text-xs text-muted mt-2">
            No links yet. Type <code className="text-brand">[[</code> in a page to link to another one.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-8" onClick={onClose}>
      <div
        className="bg-base border border-border rounded-lg w-full max-w-3xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-bold text-foreground font-display">
            Page Graph &mdash; {graph.nodes.length} pages, {graph.edges.length} links
          </h3>
          <button onClick={onClose} className="text-muted hover:text-foreground text-lg">&times;</button>
        </div>
        <div className="relative">
          <canvas
            ref={canvasRef}
            className={`w-full ${cursorClass}`}
            style={{ height: 400 }}
          />
          {tooltipEl}
        </div>
        {graph.edges.length === 0 && (
          <div className="px-4 py-3 border-t border-border">
            <p className="text-xs text-muted">
              No links yet. Type <code className="text-brand">[[</code> in a page to link to another one.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
