"use client";

import { useEffect, useRef, useState } from "react";
import type { PageGraph } from "../../lib/types";

interface PageGraphViewProps {
  graph: PageGraph;
  onClose: () => void;
  onSelectPage?: (pageId: string) => void;
}

interface SimNode {
  id: string;
  name: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export default function PageGraphView({ graph, onClose, onSelectPage }: PageGraphViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const animRef = useRef<number>(0);

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
    const nodes: SimNode[] = graph.nodes.map((n, i) => ({
      id: n.id,
      name: n.name,
      x: dw / 2 + (Math.random() - 0.5) * dw * 0.6,
      y: dh / 2 + (Math.random() - 0.5) * dh * 0.6,
      vx: 0,
      vy: 0,
    }));
    nodesRef.current = nodes;

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const edges = graph.edges.map((e) => ({
      source: nodeMap.get(e.source)!,
      target: nodeMap.get(e.target)!,
      label: e.label,
    })).filter((e) => e.source && e.target);

    const tick = () => {
      // Force simulation
      const k = 0.01; // spring constant
      const repulsion = 8000;
      const damping = 0.85;
      const centerPull = 0.005;

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
        // Bounds
        node.x = Math.max(40, Math.min(dw - 40, node.x));
        node.y = Math.max(40, Math.min(dh - 40, node.y));
      }

      // Draw
      ctx.clearRect(0, 0, dw, dh);

      // Edges
      ctx.strokeStyle = "#3E4E63";
      ctx.lineWidth = 1.5;
      for (const edge of edges) {
        ctx.beginPath();
        ctx.moveTo(edge.source.x, edge.source.y);
        ctx.lineTo(edge.target.x, edge.target.y);
        ctx.stroke();

        // Arrow
        const angle = Math.atan2(edge.target.y - edge.source.y, edge.target.x - edge.source.x);
        const arrowLen = 8;
        const mx = (edge.source.x + edge.target.x) / 2;
        const my = (edge.source.y + edge.target.y) / 2;
        ctx.beginPath();
        ctx.moveTo(mx, my);
        ctx.lineTo(mx - arrowLen * Math.cos(angle - 0.4), my - arrowLen * Math.sin(angle - 0.4));
        ctx.moveTo(mx, my);
        ctx.lineTo(mx - arrowLen * Math.cos(angle + 0.4), my - arrowLen * Math.sin(angle + 0.4));
        ctx.stroke();
      }

      // Nodes
      for (const node of nodes) {
        const isHovered = node.id === hoveredNode;
        const hasEdge = edges.some((e) => e.source.id === node.id || e.target.id === node.id);

        // Circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, isHovered ? 10 : 7, 0, Math.PI * 2);
        ctx.fillStyle = hasEdge ? "#F97316" : "#8B5CF6";
        if (isHovered) ctx.fillStyle = "#EA580C";
        ctx.fill();

        // Label
        ctx.font = `${isHovered ? "bold " : ""}11px 'Instrument Sans', sans-serif`;
        ctx.fillStyle = "#F1F5F9";
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x, node.y - 14);
      }

      animRef.current = requestAnimationFrame(tick);
    };

    animRef.current = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(animRef.current);
  }, [graph, hoveredNode]);

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
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    let found: string | null = null;
    for (const node of nodesRef.current) {
      const dx = node.x - x;
      const dy = node.y - y;
      if (dx * dx + dy * dy < 15 * 15) {
        found = node.id;
        break;
      }
    }
    setHoveredNode(found);
  };

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
        <canvas
          ref={canvasRef}
          className="w-full cursor-crosshair"
          style={{ height: 400 }}
          onClick={handleCanvasClick}
          onMouseMove={handleCanvasMove}
        />
        {graph.edges.length === 0 && (
          <div className="px-4 py-3 border-t border-border">
            <p className="text-xs text-muted">
              No links yet. Use <code className="text-brand">[[Page Name]]</code> syntax in your pages to create wiki links.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
