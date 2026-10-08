"use client";

import { ChevronRight, ArrowUpLeft } from "lucide-react";
import type { RmStep } from "@/lib/types";
import type { TraceGroup } from "./trace-outline";
import { resolveGroupPath } from "./trace-outline";
import { rowHead, readableExcerpt } from "./trace-presentation";
import { toolLabel, type TraceRow } from "./trace-rows";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";

export default function TraceExplorer({ groups, path, onPath, ann, isExpanded, onToggle }: {
  groups: TraceGroup[]; path: string[]; onPath: (path: string[]) => void; ann: StepAnnotations;
  isExpanded: (row: TraceRow) => boolean; onToggle: (row: TraceRow) => void;
}) {
  if (groups.length === 1 && groups[0].rows.length <= 8 && path.length === 0) {
    return <section aria-label="Trace explorer"><TraceTimeline rows={groups[0].rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /></section>;
  }
  const trail = resolveGroupPath(groups, path);
  const current = trail.at(-1);
  const children = current ? current.children : groups;
  const number = (step: RmStep) => ann.stepNumber?.(step) ?? step.index + 1;
  const descend = (key: string) => onPath([...trail.map((node) => node.key), key]);
  return <section aria-label="Trace explorer">
    <nav aria-label="Trace hierarchy" className="mb-5 flex min-h-8 items-center gap-1 overflow-hidden text-xs text-muted-foreground">
      <button type="button" onClick={() => onPath([])} className="shrink-0 cursor-pointer hover:text-foreground">Overview</button>
      {trail.map((node, index) => <span key={node.key} className="flex min-w-0 items-center gap-1">
        <ChevronRight className="size-3 shrink-0" aria-hidden="true" />
        <button type="button" title={node.title} onClick={() => onPath(path.slice(0, index + 1))} className="max-w-60 cursor-pointer truncate hover:text-foreground">{node.title}</button>
      </span>)}
      {current && <button type="button" aria-label="Zoom out" onClick={() => onPath(path.slice(0, -1))} className="ml-auto flex shrink-0 cursor-pointer items-center gap-1 pl-2 hover:text-foreground"><ArrowUpLeft className="size-3" />Back</button>}
    </nav>
    {current && <div className="mb-4"><h2 className="m-0 text-lg font-semibold tracking-tight">{current.title}</h2><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{current.summary}</p></div>}
    {current && !children.length ? <TraceTimeline rows={current.rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /> :
      <div className="grid gap-3">{children.map((node) => {
        const first = number(rowHead(node.rows[0]));
        const last = number(rowHead(node.rows.at(-1)!));
        return <button key={node.key} type="button" onClick={() => descend(node.key)}
          aria-label={`Explore ${node.title}`} className="group relative cursor-pointer rounded-xl border border-border-subtle bg-surface/25 px-5 py-4 text-left transition-colors hover:border-foreground/20 hover:bg-surface/60 focus-visible:outline-2 focus-visible:outline-brand-500">
          <div className="flex items-start gap-4"><h3 className="m-0 flex-1 text-[15px] font-medium leading-relaxed">{node.title}</h3><span className="mt-1 shrink-0 text-[11px] text-muted-foreground tabular-nums">{first === last ? `Step ${first}` : `Steps ${first}–${last}`}</span><ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" /></div>
          <p className="m-0 mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">{node.summary}</p>
          <div className="mt-3 flex items-center gap-3 text-[11px] text-muted-foreground"><span>{node.rows.length} steps</span><span>{node.children.length ? `${node.children.length} sections` : "Open steps"}</span></div>
          <div className="mt-3 hidden border-t border-border-subtle pt-3 text-xs leading-6 text-muted-foreground group-hover:block group-focus-visible:block" aria-hidden="true">
            {node.children.length ? node.children.slice(0, 3).map((child) => <div key={child.key} className="truncate">{child.title}</div>) : node.rows.slice(0, 3).map((row) => <div key={row.key} className="truncate">{row.kind === "tool" ? toolLabel(rowHead(row).tool_name) : readableExcerpt(rowHead(row).content)}</div>)}
          </div>
        </button>;
      })}</div>}
  </section>;
}
