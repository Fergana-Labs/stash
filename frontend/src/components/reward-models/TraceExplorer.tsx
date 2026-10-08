"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronRight, ArrowUpLeft, LayoutGrid } from "lucide-react";
import type { RmStep } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { TraceGroup } from "./trace-outline";
import { sectionFallbackTitle, traceExplorerLevel } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import type { TraceRow } from "./trace-rows";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import type { useSectionSummaries } from "./use-section-summaries";
import TraceSectionScore from "./TraceSectionScore";
import { traceSectionTarget } from "./trace-scroll";

export default function TraceExplorer({ groups, path, onPath, assessments, ann, isExpanded, onToggle, onOpenRows }: {
  groups: TraceGroup[]; path: string[]; onPath: (path: string[]) => void; ann: StepAnnotations;
  assessments: ReturnType<typeof useSectionSummaries>;
  isExpanded: (row: TraceRow) => boolean; onToggle: (row: TraceRow) => void;
  onOpenRows: (rows: TraceRow[]) => void;
}) {
  const { trail, current, children, canAscend } = traceExplorerLevel(groups, path);
  const { copy, status } = assessments;
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
    if (!node.children.length) onOpenRows(node.rows);
    onPath([...trail.map((item) => item.key), node.key]);
  }
  useEffect(() => {
    function navigate(event: KeyboardEvent) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.isComposing) return;
      const target = event.target;
      if (!(target instanceof HTMLElement) || target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="dialog"], [role="menu"], [role="listbox"]')) return;
      if (target !== document.body && !explorer.current?.contains(target)) return;
      if ((event.key === "ArrowLeft" || event.key === "Escape") && canAscend) {
        event.preventDefault();
        if (!event.repeat) ascend();
      } else if (event.key === "ArrowRight" && selected) {
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
  const title = (node: TraceGroup) => copy(node)?.title ?? sectionFallbackTitle(node);
  return <section ref={explorer} tabIndex={-1} aria-label="Trace explorer" className="outline-none">
    <nav aria-label="Trace hierarchy" className="sticky top-0 z-10 mb-2 flex h-8 bg-background items-center gap-1 overflow-hidden text-xs text-muted-foreground">
      <button type="button" onClick={() => onPath([])} className="flex shrink-0 cursor-pointer items-center gap-1.5 font-medium text-foreground hover:text-brand-600"><LayoutGrid className="size-3.5" />Sections</button>
      {trail.map((node, index) => <span key={node.key} className="flex min-w-0 items-center gap-1">
        <ChevronRight className="size-3 shrink-0" aria-hidden="true" />
        <button type="button" title={title(node)} onClick={() => onPath(trail.slice(0, index + 1).map((node) => node.key))} className="max-w-48 cursor-pointer truncate hover:text-foreground">{title(node)}</button>
      </span>)}
      {children.length > 0 && status !== "ready" && <span role="status" className="ml-auto shrink-0 text-[11px]">{status === "loading" ? "Summarizing and scoring…" : "Section assessments unavailable"}</span>}
      <span className="ml-auto hidden shrink-0 text-[11px] sm:inline">↑↓ select · → open · ← back</span>
      {canAscend && <button type="button" aria-label="Zoom out" onClick={ascend} className="ml-auto flex shrink-0 cursor-pointer items-center gap-1 pl-2 hover:text-foreground"><ArrowUpLeft className="size-3" />Back</button>}
    </nav>
    {current && !children.length ? <div>{groups.map((group) => <div key={group.key} id={traceSectionTarget(group)}><TraceTimeline rows={group.rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} /></div>)}</div> :
      <div ref={cards} data-trace-sections className="flex flex-col gap-2">{children.map((node) => {
        const generated = copy(node);
        return <div key={node.key} id={traceSectionTarget(node)} data-trace-section className="relative">
          <button type="button" onClick={() => descend(node)}
          onPointerMove={(event) => { if (event.pointerType === "mouse") select(node); }}
          onFocus={() => select(node)} data-section-key={node.key} data-selected={node.key === selected?.key}
          tabIndex={node.key === selected?.key ? 0 : -1} aria-current={node.key === selected?.key ? "true" : undefined}
          aria-label={`Explore ${title(node)}`} className={cn("flex min-h-28 w-full cursor-pointer flex-col justify-center overflow-hidden rounded-xl border bg-surface/25 py-4 pr-32 pl-4 text-left transition-colors hover:border-foreground/20 hover:bg-surface/60 focus-visible:outline-2 focus-visible:outline-brand-500", node.key === selected?.key ? "border-brand-500/50 bg-brand-500/5" : "border-border-subtle")}>
          <div className="flex w-full items-center gap-3"><h3 className="m-0 line-clamp-2 min-w-0 flex-1 text-[15px] font-medium leading-snug">{title(node)}</h3><span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{range(node)}</span><ChevronRight className="size-4 shrink-0 text-muted-foreground" /></div>
          {generated && <p className="m-0 mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">{generated.summary}</p>}
          <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground"><span>{node.rows.length} steps</span><span>{node.children.length ? `${node.children.length} subtasks` : "Open steps"}</span></div>
        </button><TraceSectionScore section={generated} range={range(node)} loading={status === "loading"} /></div>;
      })}</div>}
  </section>;
}
