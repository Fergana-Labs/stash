"use client";

import type { RefObject } from "react";
import ConversationScrollRail from "@/components/ConversationScrollRail";
import type { RmSectionCopy } from "@/lib/api";
import type { RmStep } from "@/lib/types";
import { resolveGroupPath, type TraceGroup } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import type { TraceRow } from "./trace-rows";
import { traceScrollMarkers, traceSectionTarget } from "./trace-scroll";

/** A stable whole-trace map, even while the explorer shows a nested subsection. */
export default function TraceScrollRail({ groups, path, rows, copy, stepNumber, scroller, onPath, onOpenRows, onStep }: {
  groups: TraceGroup[];
  path: string[];
  rows: TraceRow[];
  copy: (node: TraceGroup) => RmSectionCopy | undefined;
  stepNumber: (step: RmStep) => number;
  scroller: RefObject<HTMLDivElement | null>;
  onPath: (path: string[]) => void;
  onOpenRows: (rows: TraceRow[]) => void;
  onStep: (stepId: string) => void;
}) {
  // A single task still needs useful global destinations along its full trace.
  const sections = groups.length > 1 ? groups : [];
  const positions = new Map(rows.map((row, index) => [`step-${rowHead(row).id}`, index]));
  const items = sections.length ? sections.map((node) => {
    const label = `Steps ${stepNumber(rowHead(node.rows[0]))}–${stepNumber(rowHead(node.rows.at(-1)!))}`;
    const summary = copy(node);
    return { targetId: traceSectionTarget(node), title: summary?.title ?? label, preview: summary?.summary ?? "", label, emphasis: true };
  }) : traceScrollMarkers(rows, true).map((marker) => {
    const row = rows[positions.get(marker.targetId)!];
    return { ...marker, label: `Step ${stepNumber(rowHead(row))}` };
  });

  const trail = resolveGroupPath(groups, path);
  const current = trail.at(-1);
  const activeTargetId = sections.length && trail.length ? traceSectionTarget(trail[0])
    : current?.children.length ? items.findLast((item) => {
      return positions.get(item.targetId)! <= positions.get(`step-${rowHead(current.rows[0]).id}`)!;
    })?.targetId : undefined;

  return <ConversationScrollRail items={items} scroller={scroller} activeTargetId={activeTargetId} onJump={(item) => {
    const first = item === items[0];
    const node = sections.find((section) => traceSectionTarget(section) === item.targetId);
    // The first tick always returns to the top of the whole trace. Other task
    // ticks open their task from a subsection, without drilling into its leaves.
    if (first) onPath([]);
    else if (node && trail.length) {
      if (!node.children.length) onOpenRows(node.rows);
      onPath([node.key]);
    } else if (!node) onStep(item.targetId.slice("step-".length));
    requestAnimationFrame(() => {
      const container = scroller.current;
      if (!container) return;
      const target = container.querySelector<HTMLElement>(`#${CSS.escape(item.targetId)}`);
      const focus = target?.querySelector<HTMLButtonElement>("[data-section-key]")
        ?? container.querySelector<HTMLElement>('[aria-label="Trace explorer"]');
      focus?.focus({ preventScroll: true });
      if (first || node && trail.length) container.scrollTo({ top: 0, behavior: "instant" });
      else if (target) container.scrollTo({
        top: container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - 12,
        behavior: "instant",
      });
    });
  }} />;
}
