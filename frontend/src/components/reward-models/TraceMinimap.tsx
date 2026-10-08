"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceMinimap";

import { useEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
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
    if (direct && event.currentTarget.contains(direct) && event.type === "pointerdown") return Number(direct.dataset.stepIndex);
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

  return (
    <nav aria-label="Trace steps" className="select-none py-2">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {Object.entries(KINDS).filter(([kind]) => steps.some((step) => kindOf(step) === kind)).map(([kind, style]) => (
          <span key={kind} className="inline-flex items-center gap-1"><span className={cn("h-2 w-2", style.color)} />{style.label}</span>
        ))}
        <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-amber-400" />Comment</span>
        <span className="ml-auto shrink-0 tabular-nums">Step {steps[activeIndex]?.index + 1} of {steps.length}</span>
      </div>
      <div aria-label="Action credit legend" className="mb-1 flex flex-wrap items-end gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="self-center">Action credit (height)</span>
        {[
          { height: 3, label: "−1 Harmful" },
          { height: 13, label: "0 Neutral" },
          { height: 23, label: "+1 Helpful" },
        ].map(({ height, label }) => (
          <span key={label} className="inline-flex items-end gap-1.5"><span aria-hidden="true" className="w-1.5 bg-muted-foreground" style={{ height }} />{label}</span>
        ))}
        <span className="inline-flex items-end gap-1.5"><span aria-hidden="true" className="h-[3px] w-1.5 bg-muted-foreground opacity-35" />Faint: no score</span>
      </div>
      <p className="m-0 mb-1 text-[11px] text-muted-foreground">Only assistant responses and tool calls are graded. Hover a bar for its score or status.</p>
      {annotationStatus && <p role="status" className="m-0 mb-1 text-[11px] text-muted-foreground">{annotationStatus}</p>}
      <div
        className="relative flex h-[52px] touch-none items-end"
        style={{ columnGap: `min(1px, ${25 / steps.length}%)` }}
        role="group"
        aria-label="Step map"
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
          if (drag.current?.pointerId !== event.pointerId) return;
          const index = indexAt(event);
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
          const actionType = kind.label;
          const missingReason = isGradableAction(step) ? unscoredReasons?.get(step.id) ?? "awaiting score" : "not graded";
          const label = `Step ${step.index + 1}: ${actionType}${step.tool_name === null ? "" : `, ${step.tool_name}`}${score ? `, credit ${formatCredit(score.credit)}${score.stale ? ", previous annotation" : ""}` : `, ${missingReason}`}`;
          return (
            <button
              key={step.id}
              data-step-index={index}
              type="button"
              title={label}
              aria-label={label}
              aria-current={index === activeIndex ? "step" : undefined}
              tabIndex={index === activeIndex ? 0 : -1}
              onClick={(event) => {
                if (event.detail === 0) jump(index);
              }}
              onKeyDown={(event) => {
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
      </div>
      <div className="mt-1 flex justify-between border-t border-border pt-1 text-[10px] text-muted-foreground tabular-nums">
        <span>Step 1</span><span>Step {steps.length}</span>
      </div>
    </nav>
  );
}

export default function TraceMinimap(props: React.ComponentProps<typeof LatestTraceMinimap>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceMinimap {...props} />;
}
