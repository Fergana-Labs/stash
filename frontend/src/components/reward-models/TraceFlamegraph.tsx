"use client";

import { useState } from "react";
import type { RmTraceSpan } from "@/lib/types";
import { cn } from "@/lib/utils";
import { layoutSpans, spanDuration } from "./span-layout";

export default function TraceFlamegraph({ spans, onJump }: { spans: RmTraceSpan[]; onJump: (index: number) => void }) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<RmTraceSpan | null>(null);
  const { rows, durationMs } = layoutSpans(spans, collapsed);
  if (spans.length === 0) return null;

  function toggle(id: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section aria-label="Execution timeline" className="py-2">
      <div className="mb-2 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>Execution timeline</span><span>{spanDuration(durationMs)}</span>
      </div>
      <div className="grid grid-cols-[190px_1fr] text-[10px] text-muted-foreground">
        <span />
        <div className="mb-1 flex justify-between"><span>0</span><span>{spanDuration(durationMs / 2)}</span><span>{spanDuration(durationMs)}</span></div>
      </div>
      <div className="scroll-thin max-h-48 overflow-y-auto" role="tree" aria-label="Agent and tool operations">
        {rows.map(({ span, depth, startMs, durationMs: elapsed, hasChildren }) => (
          <div key={span.id} role="treeitem" aria-level={depth + 1} aria-selected={selected?.id === span.id} aria-expanded={hasChildren ? !collapsed.has(span.id) : undefined}
            className={cn("grid h-7 grid-cols-[190px_1fr] items-center border-t border-border-subtle", selected?.id === span.id && "bg-surface")}>
            <div className="flex min-w-0 items-center gap-1 pr-2" style={{ paddingLeft: depth * 12 }}>
              <button type="button" onClick={() => setSelected(span)} title={span.name} className="min-w-0 cursor-pointer truncate text-left text-[11px] text-dim">{span.name}</button>
              {hasChildren && <button type="button" aria-label={`${collapsed.has(span.id) ? "Expand" : "Collapse"} ${span.name}`} onClick={() => toggle(span.id)} className="ml-auto cursor-pointer text-[10px] text-muted-foreground">{collapsed.has(span.id) ? "Show" : "Hide"}</button>}
            </div>
            <div className="relative h-full border-l border-border">
              <button type="button" onClick={() => setSelected(span)} aria-label={`${span.name}, ${spanDuration(elapsed)}`} title={`${span.name}: starts at ${spanDuration(startMs)}, runs for ${spanDuration(elapsed)}`}
                className={cn("absolute top-1 h-5 min-w-[2px] cursor-pointer overflow-hidden px-1 text-left text-[10px] text-foreground", span.kind === "AGENT" ? "bg-amber-300/70" : span.kind === "TOOL" ? "bg-slate-300/70" : "bg-violet-200/70", selected?.id === span.id && "outline-1 outline-foreground")}
                style={{ left: durationMs === 0 ? 0 : `${startMs / durationMs * 100}%`, width: durationMs === 0 ? "2px" : `${elapsed / durationMs * 100}%` }}>
                <span className="whitespace-nowrap">{span.name}</span>
              </button>
            </div>
          </div>
        ))}
      </div>
      {selected && <div className="mt-2 border-t border-border pt-2 text-[11px]">
        <div className="flex items-center gap-2">
          <strong className="font-medium">{selected.name}</strong>
          {selected.kind && <span className="text-muted-foreground">{selected.kind.toLowerCase()}</span>}
          <span className="text-muted-foreground">{spanDuration(Number(BigInt(selected.end_ns) - BigInt(selected.start_ns)) / 1e6)}</span>
          {selected.step_indices.length > 0 && <button type="button" onClick={() => onJump(selected.step_indices[0])} className="ml-auto cursor-pointer underline">View messages</button>}
          <button type="button" onClick={() => setSelected(null)} className="ml-auto cursor-pointer text-muted-foreground">Close details</button>
        </div>
        {(selected.input !== null || selected.output !== null) && <div className="mt-1 grid grid-cols-2 gap-3">
          <SpanValue label="Input" value={selected.input} /><SpanValue label="Result" value={selected.output} />
        </div>}
      </div>}
    </section>
  );
}

function SpanValue({ label, value }: { label: string; value: string | null }) {
  return <div className="min-w-0"><div className="mb-1 text-muted-foreground">{label}</div><pre className="m-0 max-h-24 overflow-auto bg-surface p-1.5 whitespace-pre-wrap">{value === null ? "Not recorded" : value}</pre></div>;
}
