"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { ChevronRight, ArrowUpLeft } from "lucide-react";
import type { RmStep } from "@/lib/types";
import type { TraceGroup } from "./trace-outline";
import { resolveGroupPath } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import type { TraceRow } from "./trace-rows";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import { useSectionSummaries } from "./use-section-summaries";
import TraceSectionScore from "./TraceSectionScore";

export default function TraceExplorer({ traceId, groups, path, onPath, ann, isExpanded, onToggle, onOpenRows, scroller }: {
  traceId: string; groups: TraceGroup[]; path: string[]; onPath: (path: string[]) => void; ann: StepAnnotations;
  isExpanded: (row: TraceRow) => boolean; onToggle: (row: TraceRow) => void;
  onOpenRows: (rows: TraceRow[]) => void; scroller: RefObject<HTMLDivElement | null>;
}) {
  const trail = resolveGroupPath(groups, path);
  const current = trail.at(-1);
  const direct = groups.length === 1 && groups[0].rows.length <= 8 && path.length === 0;
  const children = direct ? [] : current ? current.children : groups;
  const { copy, status } = useSectionSummaries(traceId, children);
  const cards = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(480);
  const hover = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverKey = useRef<string | null>(null);
  const pathKey = path.join("/");
  const levelKey = children.map((node) => node.key).join("/");
  function cancelHover() {
    if (hover.current) clearTimeout(hover.current);
    hover.current = null;
    hoverKey.current = null;
  }
  useEffect(() => { cancelHover(); return cancelHover; }, [pathKey, levelKey]);
  useEffect(() => {
    const element = cards.current;
    const viewport = scroller.current;
    if (!element || !viewport) return;
    const measure = () => setHeight(Math.max(120, Math.floor(Math.min(window.innerHeight, viewport.getBoundingClientRect().bottom) - element.getBoundingClientRect().top - 12)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    // Context disclosure and breadcrumb wrapping also change the space available.
    if (element.parentElement?.parentElement) observer.observe(element.parentElement.parentElement);
    window.addEventListener("resize", measure);
    return () => { observer.disconnect(); window.removeEventListener("resize", measure); };
  }, [scroller, pathKey, children.length]);
  const number = (step: RmStep) => ann.stepNumber?.(step) ?? step.index + 1;
  const range = (node: TraceGroup) => {
    const first = number(rowHead(node.rows[0]));
    const last = number(rowHead(node.rows.at(-1)!));
    return first === last ? `Step ${first}` : `Steps ${first}–${last}`;
  };
  const title = (node: TraceGroup) => copy(node)?.title ?? range(node);
  function descend(node: TraceGroup, expand = false) {
    cancelHover();
    if (expand && !node.children.length) onOpenRows(node.rows);
    onPath([...trail.map((item) => item.key), node.key]);
  }
  if (direct) return <section aria-label="Trace explorer"><TraceTimeline rows={groups[0].rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /></section>;
  const cardHeight = height / Math.max(children.length, 1);
  return <section aria-label="Trace explorer" onKeyDown={(event) => {
    if (event.key === "Escape" && current) { cancelHover(); onPath(trail.slice(0, -1).map((node) => node.key)); }
  }}>
    <nav aria-label="Trace hierarchy" className="mb-2 flex h-8 items-center gap-1 overflow-hidden text-xs text-muted-foreground">
      <button type="button" onClick={() => onPath([])} className="shrink-0 cursor-pointer hover:text-foreground">Overview</button>
      {trail.map((node, index) => <span key={node.key} className="flex min-w-0 items-center gap-1">
        <ChevronRight className="size-3 shrink-0" aria-hidden="true" />
        <button type="button" title={title(node)} onClick={() => onPath(trail.slice(0, index + 1).map((node) => node.key))} className="max-w-48 cursor-pointer truncate hover:text-foreground">{title(node)}</button>
      </span>)}
      {children.length > 0 && status !== "ready" && <span role="status" className="ml-auto shrink-0 text-[11px]">{status === "loading" ? "Summarizing and scoring…" : "Section assessments unavailable"}</span>}
      {current && <button type="button" aria-label="Zoom out" onClick={() => onPath(trail.slice(0, -1).map((node) => node.key))} className="ml-auto flex shrink-0 cursor-pointer items-center gap-1 pl-2 hover:text-foreground"><ArrowUpLeft className="size-3" />Back</button>}
    </nav>
    {current && !children.length ? <TraceTimeline rows={current.rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /> :
      <div ref={cards} data-trace-sections className="flex flex-col gap-2" style={{ height }}>{children.map((node) => {
        const generated = copy(node);
        return <div key={node.key} data-trace-section className="relative min-h-0 flex-1">
          <button type="button" onClick={() => descend(node)}
          onPointerMove={(event) => {
            // Movement, rather than pointer-enter, prevents a stationary pointer
            // from cascading into newly mounted children after a hover opens a level.
            if (event.pointerType !== "mouse" || hoverKey.current === node.key) return;
            cancelHover();
            hoverKey.current = node.key;
            hover.current = setTimeout(() => descend(node, true), 450);
          }}
          onPointerLeave={cancelHover} onPointerDown={cancelHover} onBlur={cancelHover}
          aria-label={`Explore ${title(node)}`} className="flex h-full w-full cursor-pointer flex-col justify-center overflow-hidden rounded-xl border border-border-subtle bg-surface/25 py-2 pr-32 pl-4 text-left transition-colors hover:border-foreground/20 hover:bg-surface/60 focus-visible:outline-2 focus-visible:outline-brand-500">
          <div className="flex w-full items-center gap-3"><h3 className="m-0 line-clamp-2 min-w-0 flex-1 text-[15px] font-medium leading-snug">{title(node)}</h3><span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{range(node)}</span><ChevronRight className="size-4 shrink-0 text-muted-foreground" /></div>
          {cardHeight >= 90 && generated && <p className={`m-0 mt-1.5 text-[13px] leading-relaxed text-muted-foreground ${cardHeight < 130 ? "line-clamp-1" : "line-clamp-2"}`}>{generated.summary}</p>}
          {cardHeight >= 115 && <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground"><span>{node.rows.length} steps</span><span>{node.children.length ? `${node.children.length} sections` : "Open steps"}</span></div>}
        </button><TraceSectionScore section={generated} range={range(node)} loading={status === "loading"} /></div>;
      })}</div>}
  </section>;
}
