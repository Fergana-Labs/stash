"use client";

import { cn } from "@/lib/utils";
import type { RubricAnswers, RubricQuestion } from "@/lib/intuition-api";
import { describeFeature, pct, pYes, questionOptions, signed, topContributions } from "./im-helpers";
import { Bar } from "./im-ui";

/** One row per label, highlighted label in brand color. */
export function ProbabilityBars({
  probabilities,
  order,
  highlight,
  describe,
}: {
  probabilities: Record<string, number>;
  order?: string[];
  highlight?: string;
  describe?: (label: string) => string | undefined;
}) {
  const labels = order ?? Object.keys(probabilities);
  return (
    <div className="space-y-1.5">
      {labels.map((label) => {
        const p = probabilities[label] ?? 0;
        const hint = describe?.(label);
        return (
          <div key={label} className="grid grid-cols-[minmax(4rem,8rem)_1fr_3rem] items-center gap-2.5" title={hint}>
            <span className={cn("truncate font-mono text-[12px]", label === highlight ? "font-semibold text-foreground" : "text-dim")}>{label}</span>
            <Bar value={p} tone={label === highlight ? "brand" : "muted"} className="h-2" />
            <span className="text-right font-mono text-[11.5px] tabular-nums text-muted-foreground">{pct(p)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Judge answers per rubric question: P(yes) for yes/no, a small distribution otherwise. */
export function RubricAnswersView({ rubric, answers, compareWith }: { rubric: RubricQuestion[]; answers: RubricAnswers; compareWith?: RubricAnswers }) {
  if (rubric.length === 0) return <p className="m-0 text-[12px] text-muted-foreground">This version has no rubric questions.</p>;
  return (
    <ul className="m-0 list-none space-y-3 p-0">
      {rubric.map((q) => {
        const answer = answers[q.id];
        return (
          <li key={q.id} className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-foreground">{q.prompt}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">{q.id}</span>
            </div>
            {!answer ? (
              <p className="m-0 mt-1 text-[11.5px] text-muted-foreground">Not answered</p>
            ) : q.type === "noul" ? (
              <YesNo p={pYes(answer)} pB={compareWith ? pYes(compareWith[q.id]) : undefined} />
            ) : (
              <Distribution question={q} answer={answer} answerB={compareWith?.[q.id]} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function YesNo({ p, pB }: { p: number | null; pB?: number | null }) {
  const row = (value: number | null, tag?: string) => (
    <div className="grid grid-cols-[2.75rem_1fr_3rem] items-center gap-2">
      <span className="text-[11px] text-muted-foreground">{tag ?? "P(yes)"}</span>
      <Bar value={value ?? 0} tone={value != null && value >= 0.5 ? "brand" : "muted"} />
      <span className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">{pct(value)}</span>
    </div>
  );
  return (
    <div className="mt-1 space-y-1">
      {row(p, pB !== undefined ? "A yes" : undefined)}
      {pB !== undefined && row(pB, "B yes")}
    </div>
  );
}

function Distribution({ question, answer, answerB }: { question: RubricQuestion; answer: Record<string, number>; answerB?: Record<string, number> }) {
  const options = questionOptions(question);
  const top = options.reduce((best, o) => ((answer[o.key] ?? 0) > (answer[best.key] ?? 0) ? o : best), options[0]);
  return (
    <div className="mt-1 space-y-0.5">
      {options.map((o) => (
        <div key={o.key} className="grid grid-cols-[minmax(0,1fr)_6rem_3rem] items-center gap-2" title={o.label}>
          <span className={cn("truncate text-[11.5px]", o.key === top?.key ? "text-foreground" : "text-muted-foreground")}>{o.label}</span>
          <div className="space-y-0.5">
            <Bar value={answer[o.key] ?? 0} tone={o.key === top?.key ? "brand" : "muted"} />
            {answerB && <Bar value={answerB[o.key] ?? 0} />}
          </div>
          <span className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">
            {pct(answer[o.key] ?? 0)}
            {answerB && <span className="block">{pct(answerB[o.key] ?? 0)}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Signed horizontal bars: what pushed the logit toward (green) or away from (red) the label. */
export function ContributionBars({ contributions, rubric, limit = 8 }: { contributions: Record<string, number> | undefined; rubric: RubricQuestion[]; limit?: number }) {
  const top = topContributions(contributions, limit);
  if (top.length === 0) return <p className="m-0 text-[12px] text-muted-foreground">No feature contributions.</p>;
  const max = Math.max(...top.map(([, v]) => Math.abs(v)), 1e-9);
  return (
    <ul className="m-0 list-none space-y-1.5 p-0">
      {top.map(([feature, value]) => {
        const info = describeFeature(feature, rubric);
        const width = `${(Math.abs(value) / max) * 50}%`;
        return (
          <li key={feature} className="grid grid-cols-[minmax(0,1fr)_minmax(6rem,40%)_3.25rem] items-center gap-2.5">
            <div className="min-w-0" title={info.question?.prompt}>
              <div className="truncate text-[12px] text-foreground">
                {info.question?.prompt ?? info.questionId}
                {info.option !== null && <span className="text-muted-foreground"> → {info.optionLabel}</span>}
              </div>
              <div className="truncate font-mono text-[10.5px] text-muted-foreground">{feature}</div>
            </div>
            <div className="relative h-2 rounded-full bg-raised">
              <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
              <div
                className={cn("absolute inset-y-0 rounded-full", value >= 0 ? "left-1/2 bg-emerald-500/70" : "right-1/2 bg-red-500/70")}
                style={{ width }}
              />
            </div>
            <span className={cn("text-right font-mono text-[11.5px] tabular-nums", value >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
              {signed(value)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
