// Design from Priyadarshan's trace viewer (projects/trace_viewer)
"use client";

import { cn } from "@/lib/utils";
import type { RmAnnotation, RmStep } from "@/lib/types";
import { isThinking, looksLikeError } from "./trace-rows";

type Kind = "user" | "assistant" | "tool" | "system" | "error";

const HEIGHT: Record<Kind, string> = {
  user: "h-[38px]",
  assistant: "h-[24px]",
  tool: "h-[14px]",
  system: "h-[9px]",
  error: "h-[20px]",
};

const COLOR: Record<Kind, string> = {
  user: "bg-amber-600/80 dark:bg-amber-400/80",
  assistant: "bg-dim",
  tool: "bg-muted-foreground/60",
  system: "bg-slate-400/70",
  error: "bg-red-500",
};

function kindOf(step: RmStep): Kind {
  if (step.role === "user") return "user";
  if (step.role === "system") return "system";
  if (step.role === "tool") return looksLikeError(step.content) ? "error" : "tool";
  if (step.tool_name !== null) return "tool";
  return isThinking(step) ? "system" : "assistant";
}

/** What an annotated step's marker shows: − outranks +, which outranks a comment. Flagged labels don't count. */
function markerOf(annotations: RmAnnotation[]): "negative" | "positive" | "comment" | null {
  const live = annotations.filter((a) => !a.label_error);
  if (live.some((a) => a.rating === -1)) return "negative";
  if (live.some((a) => a.rating === 1)) return "positive";
  if (live.length > 0) return "comment";
  return null;
}

const MARKER: Record<"negative" | "positive" | "comment", string> = {
  negative: "bg-red-500",
  positive: "bg-green-600",
  comment: "bg-amber-400",
};

/**
 * One bar per step, height and color by kind, with a dot above steps that
 * carry annotations. Click jumps to the step; the line marks the step at the
 * top of the viewport.
 */
export default function TraceMinimap({
  steps,
  annotations,
  cursorStepId,
  onJump,
}: {
  steps: RmStep[];
  annotations: RmAnnotation[];
  cursorStepId: string | null;
  onJump: (step: RmStep) => void;
}) {
  const byStep = new Map<string, RmAnnotation[]>();
  for (const a of annotations) {
    if (a.step_id === null) continue;
    byStep.set(a.step_id, [...(byStep.get(a.step_id) ?? []), a]);
  }
  const cursorIndex = steps.findIndex((s) => s.id === cursorStepId);

  return (
    <div className="select-none">
      <div className="relative flex h-[52px] items-end gap-px" role="slider" aria-label="Trace timeline" aria-valuemin={0} aria-valuemax={steps.length - 1} aria-valuenow={Math.max(0, cursorIndex)}>
        {steps.map((step) => {
          const kind = kindOf(step);
          const marker = markerOf(byStep.get(step.id) ?? []);
          return (
            <button
              key={step.id}
              type="button"
              onClick={() => onJump(step)}
              title={`#${step.index} · ${kind === "error" ? "tool error" : kind}${step.tool_name ? ` · ${step.tool_name}` : ""}`}
              className="group relative flex h-full min-w-px flex-1 cursor-pointer flex-col items-center justify-end"
            >
              {marker && <span className={cn("absolute top-0 size-1.5 rounded-full", MARKER[marker])} />}
              <span className={cn("w-full max-w-[24px] rounded-t-[2px] transition-opacity group-hover:opacity-70", HEIGHT[kind], COLOR[kind])} />
            </button>
          );
        })}
        {cursorIndex >= 0 && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-y-0 w-[1.5px] bg-brand-500"
            style={{ left: `${((cursorIndex + 0.5) / steps.length) * 100}%` }}
          />
        )}
      </div>
      <div className="mt-1 h-px w-full bg-border" />
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground tabular-nums">
        <span>#{steps[0].index}</span>
        <span>#{steps[steps.length - 1].index}</span>
      </div>
    </div>
  );
}

export function MinimapLegend() {
  return (
    <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
      <Legend className="bg-amber-600/80" label="prompt" />
      <Legend className="bg-dim" label="assistant" />
      <Legend className="bg-muted-foreground/60" label="tool" />
      <Legend className="bg-red-500" label="error" />
      <span className="inline-flex items-center gap-1.5">
        <span className="size-1.5 rounded-full bg-green-600" />
        <span className="size-1.5 rounded-full bg-red-500" />
        annotated
      </span>
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-2.5 w-[3px] rounded-sm", className)} />
      {label}
    </span>
  );
}
