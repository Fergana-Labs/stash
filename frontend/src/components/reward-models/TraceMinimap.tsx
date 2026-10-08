"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceMinimap";

import { useEffect, useId, useRef, useState, type PointerEvent, type RefObject } from "react";
import { cn } from "@/lib/utils";
import { isThinking, looksLikeError } from "./trace-rows";
import { visibleStepElement } from "./trace-scroll";
import type { RmActionScore, RmAnnotation, RmStep } from "@/lib/types";
import { formatCredit } from "./action-credit";
import { isGradableAction } from "./automatic-credit";

// Design from Priyadarshan's trace viewer (projects/trace_viewer).
const KINDS = {
  user: { label: "User", color: "bg-amber-500" },
  system: { label: "System", color: "bg-slate-400" },
  thinking: { label: "Thinking", color: "bg-slate-400" },
  assistant: { label: "Response", color: "bg-blue-500" },
  call: { label: "Tool call", color: "bg-violet-500" },
  result: { label: "Tool result", color: "bg-teal-500" },
  error: { label: "Error", color: "bg-red-500" },
};

function kindOf(step: RmStep): keyof typeof KINDS {
  if (step.role === "user") return "user";
  if (step.role === "system") return "system";
  if (isThinking(step)) return "thinking";
  if (step.role === "tool") return looksLikeError(step.content) ? "error" : "result";
  return step.tool_name == null ? "assistant" : "call";
}

function LatestTraceMinimap({ steps, annotations, actionScores, annotationStatus, unscoredReasons, scroller, navigation, onJump }: {
  steps: RmStep[];
  annotations: RmAnnotation[];
  actionScores?: Map<string, RmActionScore>;
  annotationStatus?: string;
  unscoredReasons?: Map<string, string>;
  scroller: RefObject<HTMLDivElement | null>;
  navigation: RefObject<HTMLDivElement | null>;
  onJump: (index: number) => void;
}) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const tooltipId = useId();
  const drag = useRef<{ pointerId: number; index: number } | null>(null);

  useEffect(() => {
    const container = scroller.current;
    const header = navigation.current;
    if (!container || !header) return;
    const indices = new Map(steps.map((step, index) => [`step-${step.id}`, index]));
    let frame = 0;
    function update() {
      const element = visibleStepElement(container!, header!);
      if (element === null) return;
      const index = indices.get(element.id);
      if (index !== undefined) setActiveIndex(index);
    }
    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    }
    container.addEventListener("scroll", schedule, { passive: true });
    const observer = new ResizeObserver(schedule);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    schedule();
    return () => {
      container.removeEventListener("scroll", schedule);
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [steps, scroller, navigation]);

  if (steps.length === 0) return null;
  const commented = new Set(annotations.filter((a) => a.comment !== null).map((a) => a.step_id));

  function jump(index: number) {
    setActiveIndex(index);
    onJump(index);
  }

  function indexAt(event: PointerEvent<HTMLDivElement>) {
    const direct = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-step-index]");
    if (direct && event.currentTarget.contains(direct) && (event.type === "pointerdown" || !drag.current)) return Number(direct.dataset.stepIndex);
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button[data-step-index]")];
    let nearest = 0;
    let distance = Infinity;
    for (const [index, button] of buttons.entries()) {
      const bounds = button.getBoundingClientRect();
      if (!bounds.width) continue;
      const delta = Math.abs(event.clientX - (bounds.left + bounds.width / 2));
      if (delta < distance) { nearest = index; distance = delta; }
    }
    if (distance < Infinity) return nearest;
    const bounds = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(steps.length - 1, Math.floor((event.clientX - bounds.left) / bounds.width * steps.length)));
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.pointerId === event.pointerId) drag.current = null;
  }

  function labelFor(step: RmStep) {
    const kind = KINDS[kindOf(step)];
    const score = actionScores?.get(step.id);
    const missingReason = isGradableAction(step) ? unscoredReasons?.get(step.id) ?? "awaiting score" : "not graded";
    return `Step ${step.index + 1}: ${kind.label}${step.tool_name === null ? "" : `, ${step.tool_name}`}${score ? `, credit ${formatCredit(score.credit)}${score.stale ? ", previous annotation" : ""}` : `, ${missingReason}`}`;
  }

  return (
    <nav aria-label="Trace steps" className="flex min-w-0 flex-1 select-none items-center gap-3">
      {annotationStatus && <p role="status" className="sr-only">{annotationStatus}</p>}
      <div
        className="relative flex h-[52px] min-w-0 flex-1 touch-none items-end"
        style={{ columnGap: `min(1px, ${25 / steps.length}%)` }}
        role="group"
        aria-label="Step map"
        onPointerEnter={(event) => { if (event.pointerType !== "touch") setHoveredIndex(indexAt(event)); }}
        onPointerLeave={() => setHoveredIndex(null)}
        onPointerDown={(event) => {
          if (event.button !== 0 || drag.current !== null) return;
          event.preventDefault();
          const index = indexAt(event);
          drag.current = { pointerId: event.pointerId, index };
          event.currentTarget.setPointerCapture(event.pointerId);
          (event.currentTarget.children[index] as HTMLButtonElement).focus({ preventScroll: true });
          jump(index);
        }}
        onPointerMove={(event) => {
          const index = indexAt(event);
          if (event.pointerType !== "touch") setHoveredIndex(index);
          if (drag.current?.pointerId !== event.pointerId) return;
          if (index === drag.current.index) return;
          drag.current.index = index;
          jump(index);
        }}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
      >
        {steps.map((step, index) => {
          const kind = KINDS[kindOf(step)];
          const score = actionScores?.get(step.id);
          const label = labelFor(step);
          return (
            <button
              key={step.id}
              data-step-index={index}
              type="button"
              aria-label={label}
              aria-describedby={hoveredIndex === index ? tooltipId : undefined}
              aria-current={index === activeIndex ? "step" : undefined}
              tabIndex={index === activeIndex ? 0 : -1}
              onFocus={() => setHoveredIndex(index)}
              onBlur={() => setHoveredIndex(null)}
              onClick={(event) => {
                if (event.detail === 0) jump(index);
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") { setHoveredIndex(null); return; }
                let next: number;
                if (event.key === "ArrowRight") next = Math.min(steps.length - 1, index + 1);
                else if (event.key === "ArrowLeft") next = Math.max(0, index - 1);
                else if (event.key === "Home") next = 0;
                else if (event.key === "End") next = steps.length - 1;
                else return;
                event.preventDefault();
                (event.currentTarget.parentElement!.children[next] as HTMLButtonElement).focus();
                jump(next);
              }}
              className="group relative flex h-full min-w-0 flex-1 cursor-pointer items-end focus-visible:outline-2 focus-visible:outline-brand-500"
            >
              {commented.has(step.id) && <span className="absolute top-0 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-amber-400" />}
              <span style={{ height: score ? `${6 + (Math.max(-1, Math.min(1, score.credit)) + 1) * 20}px` : "6px" }} className={cn("w-full transition-opacity group-hover:opacity-60", kind.color, !score && "opacity-35")} />
            </button>
          );
        })}
        <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 w-[1.5px] bg-brand-500" style={{ left: `${(activeIndex + 0.5) / steps.length * 100}%` }} />
        {hoveredIndex !== null && steps[hoveredIndex] && <div
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none absolute bottom-full z-20 mb-2 w-64 max-w-full rounded-md bg-foreground px-3 py-2 text-xs text-background shadow-md"
          style={{ left: `clamp(0px, calc(${(hoveredIndex + 0.5) / steps.length * 100}% - 8rem), max(0px, calc(100% - 16rem)))` }}
        >{labelFor(steps[hoveredIndex])}</div>}
      </div>
      <span className="shrink-0 whitespace-nowrap text-[10px] text-muted-foreground tabular-nums">Step {steps[activeIndex]?.index + 1} of {steps.length}</span>
    </nav>
  );
}

export default function TraceMinimap(props: React.ComponentProps<typeof LatestTraceMinimap>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceMinimap {...props} />;
}
