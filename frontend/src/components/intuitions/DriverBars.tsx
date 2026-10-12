"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Driver, RubricAnswers, RubricQuestion } from "@/lib/intuition-api";
import { answerSummary, driverBar, driverScale, signed } from "./im-helpers";

/**
 * Why a decision came out the way it did: one row per rubric question, a diverging bar
 * (right / green pushed toward the verdict, left / red pushed against it), and the
 * judge's answer to that question when we have it.
 */
export default function DriverBars({
  drivers,
  rubric = [],
  answers,
  answersB,
  limit = 6,
  compact,
}: {
  drivers: Driver[] | undefined;
  rubric?: RubricQuestion[];
  /** Judge answers for the item (A side of a comparison). */
  answers?: RubricAnswers;
  answersB?: RubricAnswers;
  /** Rows shown before "show all". */
  limit?: number;
  compact?: boolean;
}) {
  const [all, setAll] = useState(false);
  if (!drivers || drivers.length === 0) return <p className="m-0 text-[12px] text-muted-foreground">No explanation recorded for this decision.</p>;
  const scale = driverScale(drivers);
  const shown = all ? drivers : drivers.slice(0, limit);
  return (
    <div>
      <ul className={cn("m-0 list-none p-0", compact ? "space-y-1" : "space-y-2")}>
        {shown.map((d) => {
          const question = rubric.find((q) => q.id === d.question_id);
          const a = answers ? answerSummary(question, answers[d.question_id]) : null;
          const b = answersB ? answerSummary(question, answersB[d.question_id]) : null;
          const bar = driverBar(d.contribution, scale);
          return (
            <li key={d.question_id} className={cn("grid items-center gap-2.5", compact ? "grid-cols-[minmax(0,1fr)_minmax(4rem,28%)_3rem]" : "grid-cols-[minmax(0,1fr)_minmax(5rem,32%)_3.25rem]")}>
              <div className="min-w-0" title={d.prompt}>
                <div className={cn("truncate text-foreground", compact ? "text-[11.5px]" : "text-[12px]")}>{d.prompt || d.question_id}</div>
                <div className="flex min-w-0 gap-1.5 font-mono text-[10.5px] text-muted-foreground">
                  <span className="truncate">{d.question_id}</span>
                  {(a || b) && <span className="shrink-0 text-dim">· {answersB ? `A ${a ?? "—"} · B ${b ?? "—"}` : a}</span>}
                </div>
              </div>
              <div className="relative h-2 rounded-full bg-raised" aria-hidden="true">
                <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
                <div className={cn("absolute inset-y-0 rounded-full", bar.side === "pos" ? "left-1/2 bg-emerald-500/70" : "right-1/2 bg-red-500/70")} style={{ width: `${bar.width}%` }} />
              </div>
              <span
                className={cn(
                  "text-right font-mono tabular-nums",
                  compact ? "text-[11px]" : "text-[11.5px]",
                  d.contribution >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
                )}
              >
                {signed(d.contribution)}
              </span>
            </li>
          );
        })}
      </ul>
      {drivers.length > limit && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-1.5 text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground">
          {all ? "Show fewer" : `Show all ${drivers.length} questions`}
        </button>
      )}
    </div>
  );
}
