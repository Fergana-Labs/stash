"use client";

import { useEffect, useState, type RefObject } from "react";
import { cn } from "@/lib/utils";
import { isThinking, looksLikeError } from "./trace-rows";
import type { RmAnnotation, RmStep } from "@/lib/types";

// Design from Priyadarshan's trace viewer (projects/trace_viewer).
const KINDS = {
  user: { label: "User", height: "h-[38px]", color: "bg-amber-600/80" },
  system: { label: "System", height: "h-[9px]", color: "bg-slate-400/70" },
  assistant: { label: "Assistant", height: "h-[24px]", color: "bg-dim" },
  tool: { label: "Tool", height: "h-[14px]", color: "bg-muted-foreground/60" },
  error: { label: "Error", height: "h-[20px]", color: "bg-red-500" },
};

function kindOf(step: RmStep): keyof typeof KINDS {
  if (step.role === "user") return "user";
  if (step.role === "system" || isThinking(step)) return "system";
  if (step.role === "tool") return looksLikeError(step.content) ? "error" : "tool";
  return step.tool_name === null ? "assistant" : "tool";
}

export default function TraceMinimap({ steps, annotations, scroller, navigation, onJump }: {
  steps: RmStep[];
  annotations: RmAnnotation[];
  scroller: RefObject<HTMLDivElement | null>;
  navigation: RefObject<HTMLDivElement | null>;
  onJump: (index: number) => void;
}) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const container = scroller.current!;
    const header = navigation.current!;
    const indices = new Map(steps.map((step, index) => [`step-${step.id}`, index]));
    let frame = 0;
    function update() {
      const boundary = header.getBoundingClientRect().bottom + 12;
      const elements = [...container.querySelectorAll<HTMLElement>('[id^="step-"]')];
      // The last row may be too short to reach the top beneath the sticky graph.
      const atBottom = container.scrollHeight > container.clientHeight
        && container.scrollHeight - container.scrollTop - container.clientHeight <= 1;
      if (atBottom) elements.reverse();
      for (const element of elements) {
        if (element.getClientRects().length === 0) continue;
        if (element.getBoundingClientRect().bottom <= boundary) continue;
        const index = indices.get(element.id);
        if (index !== undefined) setActiveIndex(index);
        break;
      }
    }
    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    }
    container.addEventListener("scroll", schedule, { passive: true });
    const observer = new ResizeObserver(schedule);
    observer.observe(container.firstElementChild!);
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

  return (
    <nav aria-label="Trace steps" className="select-none py-2">
      <div className="mb-2 flex items-center gap-3 text-[11px] text-muted-foreground">
        {Object.entries(KINDS).map(([kind, style]) => (
          <span key={kind} className="inline-flex items-center gap-1">
            <span className={cn("h-2 w-2", style.color)} />{style.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-amber-400" />Comment</span>
        <span className="ml-auto shrink-0 tabular-nums">Step {activeIndex + 1} of {steps.length}</span>
      </div>
      <div className="relative flex h-[52px] items-end gap-px" role="group" aria-label="Step map">
        {steps.map((step, index) => {
          const kind = KINDS[kindOf(step)];
          const label = `Step ${index + 1}: ${kind.label}${step.tool_name === null ? "" : `, ${step.tool_name}`}`;
          return (
            <button
              key={step.id}
              type="button"
              title={label}
              aria-label={label}
              aria-current={index === activeIndex ? "step" : undefined}
              tabIndex={index === activeIndex ? 0 : -1}
              onClick={() => jump(index)}
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
              <span className={cn("w-full transition-opacity group-hover:opacity-60", kind.height, kind.color)} />
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
