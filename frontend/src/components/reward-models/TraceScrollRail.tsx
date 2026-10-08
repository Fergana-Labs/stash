"use client";

import type { RefObject } from "react";
import ConversationScrollRail from "@/components/ConversationScrollRail";
import type { RmSectionCopy } from "@/lib/api";
import type { RmStep } from "@/lib/types";
import type { TraceGroup } from "./trace-outline";
import { rowHead } from "./trace-presentation";
import type { TraceRow } from "./trace-rows";
import { traceScrollMarkers, traceSectionTarget } from "./trace-scroll";

/** Scrubbing changes position within the visible level, never the hierarchy. */
export default function TraceScrollRail({ sections, rows, copy, stepNumber, scroller }: {
  sections: TraceGroup[];
  rows: TraceRow[];
  copy: (node: TraceGroup) => RmSectionCopy | undefined;
  stepNumber: (step: RmStep) => number;
  scroller: RefObject<HTMLDivElement | null>;
}) {
  const items = sections.length ? sections.map((node) => {
    const label = `Steps ${stepNumber(rowHead(node.rows[0]))}–${stepNumber(rowHead(node.rows.at(-1)!))}`;
    const summary = copy(node);
    return { targetId: traceSectionTarget(node), title: summary?.title ?? label, preview: summary?.summary ?? "", label, emphasis: true };
  }) : traceScrollMarkers(rows).map((marker) => {
    const row = rows.find((row) => `step-${rowHead(row).id}` === marker.targetId)!;
    return { ...marker, label: `Step ${stepNumber(rowHead(row))}` };
  });

  return <ConversationScrollRail items={items} scroller={scroller} onJump={(item) => {
    const container = scroller.current;
    const target = container?.querySelector<HTMLElement>(`#${CSS.escape(item.targetId)}`);
    if (!container || !target) return;
    // Hand focus back to the explorer so arrow navigation works after a scrub.
    const focus = sections.length ? target.querySelector<HTMLButtonElement>("[data-section-key]")
      : target.closest<HTMLElement>('[aria-label="Trace explorer"]');
    focus?.focus({ preventScroll: true });
    container.scrollTo({
      top: item === items[0] ? 0 : container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - 12,
      behavior: "instant",
    });
  }} />;
}
