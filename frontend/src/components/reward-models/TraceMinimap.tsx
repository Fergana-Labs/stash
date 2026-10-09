"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TraceMinimap";

import { useEffect, useId, useRef, useState, type PointerEvent, type RefObject } from "react";
import { cn } from "@/lib/utils";
import { isThinking, looksLikeError, toolLabel, toolSummary } from "./trace-rows";
import { readableExcerpt } from "./trace-presentation";
import { TRACE_STEP_INSET, visibleStepElement } from "./trace-scroll";
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

function StepPreview({ step, score, status }: { step: RmStep; score?: RmActionScore; status?: string }) {
  const timestamp = step.metadata?.timestamp;
  const time = typeof timestamp === "string" ? new Date(timestamp) : null;
  const recordedTitle = step.tool_input?.title ?? step.tool_input?.description;
  const detail = typeof recordedTitle === "string" && recordedTitle.trim()
    ? recordedTitle : toolSummary(step.tool_input);
  const summary = readableExcerpt(step.content, 180) || (step.tool_name
    ? `${toolLabel(step.tool_name)}${detail ? `: ${detail.replace(/\s+/g, " ").trim()}` : ""}`
    : step.images?.length ? "Attached an image" : `${KINDS[kindOf(step)].label} message`);
  return <>
    <span className="flex shrink-0 items-center gap-2 text-[11px] tabular-nums opacity-70">
      <span>({step.index + 1})</span>
      {time && Number.isFinite(time.getTime()) && <time dateTime={timestamp as string}>{time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>}
    </span>
    <span className="min-w-0 flex-1 truncate">{summary.length > 180 ? `${summary.slice(0, 180).trimEnd()}…` : summary}</span>
    {(score || status) && <span className="max-w-40 shrink-0 truncate text-[11px] opacity-70">{score ? `Credit ${formatCredit(score.credit)}${score.stale ? " · previous annotation" : ""}` : status}</span>}
  </>;
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
  const [scale, setScale] = useState<"fit" | "fixed">("fixed");
  const tooltipId = useId();
  const root = useRef<HTMLElement>(null);
  const map = useRef<HTMLDivElement>(null);
  const selectedStep = useRef<string | null>(null);
  const drag = useRef<{ pointerId: number; index: number } | null>(null);

  useEffect(() => {
    const container = scroller.current;
    const header = navigation.current;
    if (!container || !header) return;
    const indices = new Map(steps.map((step, index) => [`step-${step.id}`, index]));
    let frame = 0;
    function update() {
      // Near the bottom, a jump can be clamped before its row reaches the header.
      // Keep the explicit selection through scrolling, layout shifts and polling.
      const selected = selectedStep.current === null ? undefined : indices.get(selectedStep.current);
      if (selected !== undefined) { setActiveIndex(selected); return; }
      selectedStep.current = null;
      const element = visibleStepElement(container!, header!, TRACE_STEP_INSET);
      if (element === null) return;
      const index = indices.get(element.id);
      if (index !== undefined) setActiveIndex(index);
    }
    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    }
    function followScroll() { selectedStep.current = null; }
    function navigateElsewhere(event: globalThis.PointerEvent) {
      if (!root.current?.contains(event.target as Node)) followScroll();
    }
    function scrollWithKeyboard(event: KeyboardEvent) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (root.current?.contains(target) || target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) return;
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(event.key)) followScroll();
    }
    container.addEventListener("wheel", followScroll, { passive: true });
    container.addEventListener("touchmove", followScroll, { passive: true });
    document.addEventListener("pointerdown", navigateElsewhere, true);
    document.addEventListener("keydown", scrollWithKeyboard, true);
    container.addEventListener("scroll", schedule, { passive: true });
    const observer = new ResizeObserver(schedule);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    schedule();
    return () => {
      container.removeEventListener("wheel", followScroll);
      container.removeEventListener("touchmove", followScroll);
      document.removeEventListener("pointerdown", navigateElsewhere, true);
      document.removeEventListener("keydown", scrollWithKeyboard, true);
      container.removeEventListener("scroll", schedule);
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [steps, scroller, navigation]);

  if (!steps.length) return null;
  const graded = steps.some((step) => Number.isFinite(actionScores?.get(step.id)?.credit));
  const maxCredit = steps.reduce((max, step) => {
    const credit = actionScores?.get(step.id)?.credit;
    return typeof credit === "number" && Number.isFinite(credit) ? Math.max(max, Math.min(1, Math.abs(credit))) : max;
  }, 0);
  const limit = scale === "fit" && maxCredit > 0 ? maxCredit : 1;
  const limitLabel = String(Number(limit.toPrecision(4)));
  const commented = new Set(annotations.filter((a) => a.comment !== null).map((a) => a.step_id));

  function jump(index: number) {
    selectedStep.current = `step-${steps[index].id}`;
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
    const missingReason = isGradableAction(step) ? unscoredReasons?.get(step.id) ?? "awaiting score" : "";
    return `Step ${step.index + 1}: ${kind.label}${step.tool_name === null ? "" : `, ${step.tool_name}`}${score ? `, credit ${formatCredit(score.credit)}${score.stale ? ", previous annotation" : ""}` : missingReason ? `, ${missingReason}` : ""}`;
  }

  return (
    <nav ref={root} aria-label="Trace steps" className="flex min-w-0 flex-1 select-none items-center gap-3">
      {annotationStatus && <p role="status" className="sr-only">{annotationStatus}</p>}
      {graded && <div aria-label={`Step credit scale: −${limitLabel} to +${limitLabel}, with zero in the middle`} style={{ width: `${limitLabel.length + 1}ch` }} className="relative h-12 shrink-0 text-right text-[9px] leading-none text-muted-foreground tabular-nums">
        <span className="absolute top-0 right-0">+{limitLabel}</span>
        <span className="absolute top-1/2 right-0 -translate-y-1/2">0</span>
        <span className="absolute right-0 bottom-0">−{limitLabel}</span>
      </div>}
      <div
        ref={map}
        className={cn("relative flex min-w-0 flex-1 touch-none", graded ? "h-12" : "h-6")}
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
          const credit = score && Number.isFinite(score.credit) ? Math.max(-1, Math.min(1, score.credit)) : null;
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
              {(credit === null || credit === 0) && <span aria-hidden="true" data-zero-marker className={cn("absolute top-1/2 z-10 h-px w-full -translate-y-1/2", kind.color)} />}
              <span aria-hidden="true" data-credit-bar style={{ height: `${Math.abs(credit ?? 0) / limit * 50}%`, ...(credit !== null && credit < 0 ? { top: "50%" } : { bottom: "50%" }) }} className={cn("absolute w-full transition-opacity group-hover:opacity-60", kind.color)} />
            </button>
          );
        })}
        <span aria-hidden="true" data-zero-baseline className="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-border-subtle" />
        <span aria-hidden="true" data-active-step-marker className="pointer-events-none absolute inset-y-0 w-[1.5px] bg-brand-500" style={{ left: `${(activeIndex + 0.5) / steps.length * 100}%` }} />
        {hoveredIndex !== null && steps[hoveredIndex] && <div
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none absolute top-full z-20 mt-2 flex h-8 w-[40rem] max-w-full items-center gap-2 overflow-hidden whitespace-nowrap rounded-md bg-foreground px-3 text-xs text-background shadow-md"
          style={{ left: `clamp(0px, calc(${(hoveredIndex + 0.5) / steps.length * 100}% - 20rem), max(0px, calc(100% - 40rem)))` }}
        ><StepPreview step={steps[hoveredIndex]} score={actionScores?.get(steps[hoveredIndex].id)} status={isGradableAction(steps[hoveredIndex]) ? unscoredReasons?.get(steps[hoveredIndex].id) ?? "awaiting score" : undefined} /></div>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="whitespace-nowrap text-[10px] text-muted-foreground tabular-nums">Step {steps[activeIndex]?.index + 1} of {steps.length}</span>
        {graded && <div role="group" aria-label="Credit scale" className="flex rounded-md border border-border-subtle p-0.5 text-[10px]">
          {([['fit', 'Fit', 'Scale to the largest absolute step credit'], ['fixed', '±1', 'Use a fixed −1 to +1 scale']] as const).map(([value, label, title]) => <button
            key={value} type="button" aria-pressed={scale === value} title={title} onClick={() => setScale(value)}
            className={cn("cursor-pointer rounded px-1.5 py-0.5 leading-none focus-visible:outline-2 focus-visible:outline-brand-500", scale === value ? "bg-surface text-foreground" : "text-muted-foreground hover:text-foreground")}
          >{label}</button>)}
        </div>}
      </div>
    </nav>
  );
}

export default function TraceMinimap(props: React.ComponentProps<typeof LatestTraceMinimap>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTraceMinimap {...props} />;
}
