"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronRight, ListTree } from "lucide-react";
import type { RmStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { TraceGroup } from "./trace-outline";
import { isContextGroup, sectionFallbackTitle, traceExplorerLevel } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import { rowSteps, type TraceRow } from "./trace-rows";
import { isGradableAction } from "./automatic-credit";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import type { useSectionSummaries } from "./use-section-summaries";
import TraceSectionScore from "./TraceSectionScore";
import { traceSectionTarget } from "./trace-scroll";

export default function TraceExplorer({ groups, path, onPath, assessments, ann, isExpanded, onToggle }: {
  groups: TraceGroup[]; path: string[]; onPath: (path: string[]) => void; ann: StepAnnotations;
  assessments: ReturnType<typeof useSectionSummaries>;
  isExpanded: (row: TraceRow) => boolean; onToggle: (row: TraceRow) => void;
}) {
  const { trail, current, children, canAscend } = traceExplorerLevel(groups, path);
  const { copy, status } = assessments;
  const taskRows = groups.flatMap((group) => group.rows);
  const explorer = useRef<HTMLElement>(null);
  const cards = useRef<HTMLDivElement>(null);
  const [selections, setSelections] = useState<Record<string, string>>({});
  const pathKey = trail.map((node) => node.key).join("/");
  const selected = children.find((node) => node.key === selections[pathKey]) ?? children[0];
  function select(node: TraceGroup, focus = false) {
    setSelections((previous) => previous[pathKey] === node.key ? previous : { ...previous, [pathKey]: node.key });
    if (focus) {
      const target = cards.current?.querySelector<HTMLButtonElement>(`[data-section-key="${node.key}"]`);
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest", behavior: "instant" });
    }
  }
  function focusLevel() {
    requestAnimationFrame(() => {
      const target = cards.current?.querySelector<HTMLButtonElement>('[data-selected="true"]') ?? explorer.current;
      target?.focus({ preventScroll: true });
      // Entering steps already scrolls to the selected section's first row.
      if (target !== explorer.current) target?.scrollIntoView?.({ block: "nearest", behavior: "instant" });
    });
  }
  function ascend() {
    if (!current || !canAscend) return;
    const parent = trail.slice(0, -1).map((node) => node.key);
    setSelections((previous) => ({ ...previous, [parent.join("/")]: current.key }));
    onPath(parent);
    focusLevel();
  }
  function descend(node: TraceGroup) {
    select(node);
    onPath([...trail.map((item) => item.key), node.key]);
  }
  useEffect(() => {
    function navigate(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.isComposing) return;
      const target = event.target;
      if (!(target instanceof HTMLElement) || target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="dialog"], [role="menu"], [role="listbox"]')) return;
      if (target !== document.body && !explorer.current?.contains(target)) return;
      if ((event.key === "Escape" || event.key === "ArrowLeft") && canAscend) {
        if (event.key === "ArrowLeft" && window.getSelection()?.isCollapsed === false) return;
        event.preventDefault();
        if (!event.repeat) ascend();
      } else if ((event.key === "Enter" || event.key === "ArrowRight") && selected && (target === document.body || target === explorer.current || target.closest("[data-section-key]"))) {
        event.preventDefault();
        if (!event.repeat) { descend(selected); focusLevel(); }
      } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && children.length) {
        event.preventDefault();
        const next = Math.max(0, Math.min(children.length - 1, children.indexOf(selected) + (event.key === "ArrowDown" ? 1 : -1)));
        select(children[next], true);
      }
    }
    document.addEventListener("keydown", navigate);
    return () => document.removeEventListener("keydown", navigate);
  });
  const number = (step: RmStep) => ann.stepNumber?.(step) ?? step.index + 1;
  const range = (node: TraceGroup) => {
    const first = number(rowHead(node.rows[0]));
    const last = number(rowHead(node.rows.at(-1)!));
    return first === last ? `Step ${first}` : `Steps ${first}–${last}`;
  };
  const title = (node: TraceGroup) => isContextGroup(node) ? "Context" : copy(node)?.title ?? sectionFallbackTitle(node);
  const assessmentStatus = children.length > 0 && status !== "ready"
    ? <span role="status" className="ml-auto shrink-0 text-[11px] text-muted-foreground">{status === "loading" ? "Summarizing and scoring…" : "Section assessments unavailable"}</span>
    : null;
  return <section ref={explorer} tabIndex={-1} aria-label="Trace explorer" className="outline-none">
    {trail.length > 0 ? <nav aria-label="Trace hierarchy" className="sticky top-0 z-10 mb-2 flex h-8 bg-background items-center gap-1 overflow-hidden text-xs text-muted-foreground">
      {canAscend && <button type="button" onClick={() => onPath([])} aria-label="Back to sections" title="Back to sections" className="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded text-muted-foreground hover:bg-surface hover:text-foreground"><ListTree className="size-4" aria-hidden="true" /></button>}
      {trail.map((node, index) => <span key={node.key} className="flex min-w-0 items-center gap-1">
        {(canAscend || index > 0) && <ChevronRight className="size-3 shrink-0" aria-hidden="true" />}
        {index === trail.length - 1 ? <span aria-current="location" title={title(node)} className="max-w-64 truncate">{title(node)}</span> : <button type="button" title={title(node)} onClick={() => onPath(trail.slice(0, index + 1).map((node) => node.key))} className="max-w-48 cursor-pointer truncate hover:text-foreground">{title(node)}</button>}
      </span>)}
      {assessmentStatus}
    </nav> : assessmentStatus && <div className="mb-2 flex">{assessmentStatus}</div>}
    {current && !children.length ? <div key={current.key} id={traceSectionTarget(current)}><TraceTimeline rows={current.rows} taskRows={taskRows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /></div> :
      <div ref={cards} data-trace-sections className="flex flex-col">{children.map((node) => {
        const generated = copy(node);
        if (isContextGroup(node)) return <div key={node.key} id={traceSectionTarget(node)} data-trace-section>
          <button type="button" onClick={() => descend(node)}
            onPointerMove={(event) => { if (event.pointerType === "mouse") select(node); }}
            onFocus={() => select(node)} data-section-key={node.key} data-selected={node.key === selected?.key}
            tabIndex={node.key === selected?.key ? 0 : -1} aria-current={node.key === selected?.key ? "true" : undefined}
            aria-label="Explore Context" className={cn("flex h-7 w-full cursor-pointer items-center gap-2 rounded-sm px-3 text-left text-xs text-muted-foreground hover:bg-surface/60 hover:text-foreground focus-visible:outline-2 focus-visible:outline-brand-500", node.key === selected?.key && "bg-surface/60")}>
            <ChevronRight className="size-3.5" aria-hidden="true" /><span>Context</span><span className="ml-auto text-[11px]">{range(node)}</span>
          </button>
        </div>;
        return <div key={node.key} id={traceSectionTarget(node)} data-trace-section className="relative">
          <button type="button" onClick={() => descend(node)}
          onPointerMove={(event) => { if (event.pointerType === "mouse") select(node); }}
          onFocus={() => select(node)} data-section-key={node.key} data-selected={node.key === selected?.key}
          tabIndex={node.key === selected?.key ? 0 : -1} aria-current={node.key === selected?.key ? "true" : undefined}
          aria-label={`Explore ${title(node)}`} title={generated?.summary}
          className={cn("flex h-7 w-full cursor-pointer items-center gap-3 overflow-hidden rounded-sm pr-24 pl-3 text-left hover:bg-surface/60 focus-visible:outline-2 focus-visible:outline-brand-500", node.key === selected?.key && "bg-surface")}>
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <h3 className="m-0 max-w-[45%] shrink-0 truncate text-[13px] font-medium leading-5">{title(node)}</h3>
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{generated?.summary}</span>
          {node.children.length > 0 && <span className="shrink-0 text-[11px] text-muted-foreground">{node.children.length} subtasks</span>}
          <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{range(node)}</span>
        </button><TraceSectionScore section={generated} range={range(node)} loading={status === "loading"} hasActions={node.rows.some((row) => rowSteps(row).some(isGradableAction))} /></div>;
      })}</div>}
  </section>;
}
