"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { LabelChip, LabelSummaryItem, LabelTone } from "./step-labels";

const TONE: Record<LabelTone, string> = {
  neutral: "bg-foreground/[0.06] text-muted-foreground",
  info: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  good: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  bad: "bg-red-500/10 text-red-600 dark:text-red-400",
};

const DOT: Record<LabelTone, string> = {
  neutral: "bg-muted-foreground/50",
  info: "bg-sky-500",
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
};

const CHIP = "inline-flex h-[18px] shrink-0 items-center rounded px-1.5 text-[10.5px] leading-none font-medium whitespace-nowrap";

/** The labels on one step. Chips that point at another step are buttons that jump to it. */
export function StepLabelChips({ chips, onJump, className }: { chips: LabelChip[]; onJump: (stepId: string) => void; className?: string }) {
  if (chips.length === 0) return null;
  return (
    <span className={cn("flex min-w-0 flex-wrap items-center gap-1", className)} onClick={(e) => e.stopPropagation()}>
      {chips.map((chip) =>
        chip.targetStepId === undefined ? (
          <span key={chip.text} title={chip.title} className={cn(CHIP, TONE[chip.tone])}>
            {chip.text}
          </span>
        ) : (
          <button
            key={chip.text}
            type="button"
            title={chip.title}
            onClick={() => onJump(chip.targetStepId!)}
            className={cn(CHIP, TONE[chip.tone], "cursor-pointer underline decoration-current/30 underline-offset-2 hover:decoration-current")}
          >
            {chip.text}
          </button>
        ),
      )}
    </span>
  );
}

/** Trace-level label counts. Each count steps through the matching steps on repeated clicks. */
export function TraceLabelSummary({ items, onJump }: { items: LabelSummaryItem[]; onJump: (stepId: string) => void }) {
  const [cursor, setCursor] = useState<Record<string, number>>({});
  if (items.length === 0) return null;
  return (
    <section aria-label="Labels" className="mb-3 flex flex-wrap items-center gap-x-1 gap-y-1 text-[12px] text-muted-foreground">
      <span className="mr-1 text-[11px] font-medium text-muted-foreground">Labels</span>
      {items.map((item) => {
        const position = cursor[item.key] ?? -1;
        return (
          <button
            key={item.key}
            type="button"
            title={item.stepIds.length > 1 ? "Click to step through them" : "Jump to it"}
            onClick={() => {
              const next = (position + 1) % item.stepIds.length;
              setCursor({ ...cursor, [item.key]: next });
              onJump(item.stepIds[next]);
            }}
            className="inline-flex h-6 cursor-pointer items-center gap-1.5 rounded-md border border-border-subtle px-2 text-[11.5px] text-foreground transition-colors hover:border-foreground/25 hover:bg-surface"
          >
            <span aria-hidden="true" className={cn("h-1.5 w-1.5 rounded-full", DOT[item.tone])} />
            {item.text}
            {position >= 0 && item.stepIds.length > 1 && (
              <span className="text-[10.5px] text-muted-foreground tabular-nums">{position + 1}/{item.stepIds.length}</span>
            )}
          </button>
        );
      })}
    </section>
  );
}
