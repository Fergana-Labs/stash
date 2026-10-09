"use client";

import type { RefObject } from "react";
import ConversationScrollRail from "@/components/ConversationScrollRail";
import type { RmSectionCopy } from "@/lib/api";
import type { RmStep } from "@/lib/types";
import { sectionFallbackTitle, traceExplorerLevel, tracePhases, type TraceGroup } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import type { TraceRow } from "./trace-rows";
import { TRACE_STEP_INSET, traceScrollMarkers } from "./trace-scroll";

/** A stable whole-trace map, even while the explorer shows a nested subsection. */
export default function TraceScrollRail({ groups, path, rows, copy, stepNumber, scroller, onPath, onStep, focusedStepId }: {
  focusedStepId?: string;
  groups: TraceGroup[];
  path: string[];
  rows: TraceRow[];
  copy: (node: TraceGroup) => RmSectionCopy | undefined;
  stepNumber: (step: RmStep) => number;
  scroller: RefObject<HTMLDivElement | null>;
  onPath: (path: string[]) => void;
  onStep: (stepId: string) => void;
}) {
  // Preserve the whole sequence at every depth. Strong ticks mark phase starts,
  // rather than collapsing a long single task into one tiny destination.
  const phaseStarts = new Map(tracePhases(groups).map(({ node }) => [rowHead(node.rows[0]).id, node]));
  const items = traceScrollMarkers(rows, true).map((marker, index) => {
    const step = rowHead(rows[index]);
    const phase = phaseStarts.get(step.id);
    const summary = phase && copy(phase);
    return { ...marker, label: `Step ${stepNumber(step)}`,
      ...(phase && { title: summary?.title ?? sectionFallbackTitle(phase), emphasis: true }),
    };
  });
  const { current, children } = traceExplorerLevel(groups, path);
  const activeTargetId = focusedStepId ? `step-${focusedStepId}`
    : children.length ? `step-${rowHead((current ?? groups[0]).rows[0]).id}` : undefined;

  return <ConversationScrollRail items={items} scroller={scroller} activeTargetId={activeTargetId} onJump={(item) => {
    const first = item === items[0];
    if (first) onPath([]);
    else onStep(item.targetId.slice("step-".length));
    requestAnimationFrame(() => {
      const container = scroller.current;
      if (!container) return;
      const target = container.querySelector<HTMLElement>(`#${CSS.escape(item.targetId)}`);
      const focus = target?.querySelector<HTMLButtonElement>("[data-section-key]")
        ?? container.querySelector<HTMLElement>('[aria-label="Trace explorer"]');
      focus?.focus({ preventScroll: true });
      if (first) container.scrollTo({ top: 0, behavior: "instant" });
      else if (target) container.scrollTo({
        top: container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - TRACE_STEP_INSET,
        behavior: "instant",
      });
    });
  }} />;
}
