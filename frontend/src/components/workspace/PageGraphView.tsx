"use client";

import { useEffect, useRef, useState } from "react";
import type { PageGraph } from "../../lib/types";

interface PageGraphViewProps {
  graph: PageGraph;
  onClose: () => void;
  onSelectPage?: (pageId: string) => void;
  inline?: boolean;
}

interface SimNode {
  id: string;
  name: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface TooltipInfo {
  x: number;
  y: number;
  name: string;
}

export default function PageGraphView({ graph, onClose, onSelectPage, inline }: PageGraphViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);
  const [overNode, setOverNode] = useState(false);
  const hoveredRef = useRef<string | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const animRef = useRef<number>(0);
  const tickRef = useRef(0);
  const clickable = Boolean(onSelectPage);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = canvas.width = canvas.offsetWidth * 2;
    const h = canvas.height = canvas.offsetHeight * 2;
    ctx.scale(2, 2);
    const dw = w / 2;
    const dh = h / 2;

    // Initialize nodes with random positions
    const nodes: SimNode[] = graph.nodes.map((n) => ({
      id: n.id,
      name: n.name,
      x: dw / 2 + (Math.random() - 0.5) * dw * 0.6,
      y: dh / 2 + (Math.random() - 0.5) * dh * 0.6,
      vx: 0,
      vy: 0,
    }));
    nodesRef.current = nodes;
    tickRef.current = 0;

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const edges = graph.edges.map((e) => ({
      source: nodeMap.get(e.source)!,
      target: nodeMap.get(e.target)!,
      label: e.label,
    })).filter((e) => e.source && e.target);

    const tick = () => {
      tickRef.current++;

      // Decay simulation energy over time — settle after ~200 ticks
      const cooling = Math.max(0.01, 1 - tickRef.current / 200);
      const k = 0.01 * cooling;
      const repulsion = 8000 * cooling;
      const damping = 0.85;
      const centerPull = 0.005 * cooling;

      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = repulsion / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          nodes[i].vx += fx;
          nodes[i].vy += fy;
          nodes[j].vx -= fx;
          nodes[j].vy -= fy;
        }
      }

      // Spring force along edges
      for (const edge of edges) {
        const dx = edge.target.x - edge.source.x;
        const dy = edge.target.y - edge.source.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const idealDist = 120;
        const force = k * (dist - idealDist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        edge.source.vx += fx;
        edge.source.vy += fy;
        edge.target.vx -= fx;
        edge.target.vy -= fy;
      }

      // Center pull + damping + update positions
      for (const node of nodes) {
        node.vx += (dw / 2 - node.x) * centerPull;
        node.vy += (dh / 2 - node.y) * centerPull;
        node.vx *= damping;
        node.vy *= damping;
        node.x += node.vx;
        node.y += node.vy;
        node.x = Math.max(40, Math.min(dw - 40, node.x));
        node.y = Math.max(40, Math.min(dh - 40, node.y));
      }

      // Draw
      const hovered = hoveredRef.current;
      ctx.clearRect(0, 0, dw, dh);

      // Build a set of bidirectional edge pairs so we only draw each line once
      const bidir = new Set<string>();
      const drawn = new Set<string>();
      for (const e of edges) {
        const rev = edges.find((o) => o.source.id === e.target.id && o.target.id === e.source.id);
        if (rev) {
          bidir.add(e.source.id + ":" + e.target.id);
          bidir.add(e.target.id + ":" + e.source.id);
        }
      }

      const drawArrow = (tipX: number, tipY: number, angle: number) => {
        const len = 8;
        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - len * Math.cos(angle - 0.4), tipY - len * Math.sin(angle - 0.4));
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(tipX - len * Math.cos(angle + 0.4), tipY - len * Math.sin(angle + 0.4));
        ctx.stroke();
      };

      // Edges
      ctx.strokeStyle = "#3E4E63";
      ctx.lineWidth = 1.5;
      for (const edge of edges) {
        const key = edge.source.id + ":" + edge.target.id;
        const isBidir = bidir.has(key);

        // For bidirectional edges, only draw once (skip the reverse)
        if (isBidir) {
          const canonKey = [edge.source.id, edge.target.id].sort().join(":");
          if (drawn.has(canonKey)) continue;
          drawn.add(canonKey);
        }

        // Line
        ctx.beginPath();
        ctx.moveTo(edge.source.x, edge.source.y);
        ctx.lineTo(edge.target.x, edge.target.y);
        ctx.stroke();

        const angle = Math.atan2(edge.target.y - edge.source.y, edge.target.x - edge.source.x);
        const nodeRadius = 10;

        if (isBidir) {
          // Arrows at both ends, just outside each node
          const tipTargetX = edge.target.x - Math.cos(angle) * nodeRadius;
          const tipTargetY = edge.target.y - Math.sin(angle) * nodeRadius;
          drawArrow(tipTargetX, tipTargetY, angle);

          const tipSourceX = edge.source.x + Math.cos(angle) * nodeRadius;
          const tipSourceY = edge.source.y + Math.sin(angle) * nodeRadius;
          drawArrow(tipSourceX, tipSourceY, angle + Math.PI);
        } else {
          // Single arrow near the target node
          const tipX = edge.target.x - Math.cos(angle) * nodeRadius;
          const tipY = edge.target.y - Math.sin(angle) * nodeRadius;
          drawArrow(tipX, tipY, angle);
        }
      }

      // Nodes
      for (const node of nodes) {
        const isHovered = node.id === hovered;
        const hasEdge = edges.some((e) => e.source.id === node.id || e.target.id === node.id);

        ctx.beginPath();
        ctx.arc(node.x, node.y, isHovered ? 10 : 7, 0, Math.PI * 2);
        ctx.fillStyle = isHovered ? "#EA580C" : hasEdge ? "#F97316" : "#8B5CF6";
        ctx.fill();

      }

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(animRef.current);
  }, [graph]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !onSelectPage) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    for (const node of nodesRef.current) {
      const dx = node.x - x;
      const dy = node.y - y;
      if (dx * dx + dy * dy < 15 * 15) {
        onSelectPage(node.id);
        return;
      }
    }
  };

  const handleCanvasMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    let found: SimNode | null = null;
    for (const node of nodesRef.current) {
      const dx = node.x - mx;
      const dy = node.y - my;
      if (dx * dx + dy * dy < 15 * 15) {
        found = node;
        break;
      }
    }
    hoveredRef.current = found?.id ?? null;
    setOverNode(!!found);
    if (found) {
      setTooltip({ x: mx, y: my, name: found.name });
    } else {
      setTooltip(null);
    }
  };

  const tooltipEl = tooltip && (
    <div
      className="absolute z-10 bg-base border border-border rounded-md px-3 py-1.5 pointer-events-none shadow-lg"
      style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
    >
      <div className="text-xs font-medium text-brand underline underline-offset-2">
        {tooltip.name}
      </div>
      {clickable && (
        <div className="text-[10px] text-muted mt-0.5">Click to open ↗</div>
      )}
    </div>
  );

  const cursorClass = clickable && overNode ? "cursor-pointer" : "cursor-default";

  if (inline) {
    return (
      <div ref={containerRef} className="relative">
        <div className="mb-2">
          <span className="text-xs text-muted">
            {graph.nodes.length} pages, {graph.edges.length} links
          </span>
        </div>
        <canvas
          ref={canvasRef}
          className={`w-full ${cursorClass} rounded`}
          style={{ height: 320 }}
          onClick={handleCanvasClick}
          onMouseMove={handleCanvasMove}
          onMouseLeave={() => { hoveredRef.current = null; setOverNode(false); setTooltip(null); }}
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
            onClick={handleCanvasClick}
            onMouseMove={handleCanvasMove}
            onMouseLeave={() => { hoveredRef.current = null; setOverNode(false); setTooltip(null); }}
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
