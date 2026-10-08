"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { LabelTone } from "./step-labels";
import { scoreParts, scoreTone, signed, type StepReward, type TaskScore } from "./step-rewards";

const TONE: Record<LabelTone, string> = {
  neutral: "bg-foreground/[0.06] text-muted-foreground",
  info: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  good: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  bad: "bg-red-500/10 text-red-600 dark:text-red-400",
};

const TEXT_TONE: Record<LabelTone, string> = {
  neutral: "text-muted-foreground",
  info: "text-sky-700 dark:text-sky-300",
  good: "text-emerald-700 dark:text-emerald-300",
  warn: "text-amber-800 dark:text-amber-300",
  bad: "text-red-600 dark:text-red-400",
};

/** A plain signed number, for sums shown on a turn. */
export function PointsChip({ points, title }: { points: number; title: string }) {
  return (
    <span title={title} className={cn("inline-flex h-[18px] shrink-0 items-center rounded px-1.5 font-mono text-[10.5px] leading-none tabular-nums", TONE[scoreTone(points)])}>
      {signed(points)}
    </span>
  );
}

/** A task's score: the final answer's points plus the cost of the work. */
export function TaskScoreChip({ score }: { score: TaskScore }) {
  return (
    <span
      title="Score for this task, from −1 (bad) to +1 (good): the final answer's points plus the cost of all the work that led to it."
      className={cn("inline-flex h-[18px] shrink-0 items-center rounded px-1.5 font-mono text-[10.5px] leading-none font-semibold tabular-nums", TONE[scoreTone(score.score)])}
    >
      {signed(score.score)}
    </span>
  );
}

/** How the score was built: one line per piece, then the total. */
export function StepScoreLine({ reward, stepNumberOf, onJumpToChunk, className }: {
  reward: StepReward;
  stepNumberOf: (chunk: string) => number | null;
  onJumpToChunk: (chunk: string) => void;
  className?: string;
}) {
  const parts = scoreParts(reward, stepNumberOf);
  return (
    <dl className={cn("m-0 max-w-xl text-[11.5px] leading-[18px] text-muted-foreground", className)} onClick={(e) => e.stopPropagation()}>
      {parts.map((part, index) => (
        <div key={`${part.text}-${index}`} className="flex items-baseline gap-3">
          <dt className="min-w-0 flex-1">
            {part.targetChunk === undefined ? (
              <span title={part.title} className={cn("cursor-help", part.tone !== "neutral" && TEXT_TONE[part.tone], part.replaced !== undefined && "opacity-70")}>{part.text}</span>
            ) : (
              <button type="button" title={part.title} onClick={() => onJumpToChunk(part.targetChunk!)}
                className={cn("cursor-pointer text-left underline decoration-current/30 underline-offset-2 hover:decoration-current", TEXT_TONE[part.tone])}>
                {part.text}
              </button>
            )}
          </dt>
          <dd className="m-0 shrink-0 font-mono tabular-nums">
            {part.replaced !== undefined
              ? <span className="line-through opacity-60" title="Replaced by the quality check below">{signed(part.replaced)}</span>
              : <span className="text-foreground">{signed(part.value ?? 0)}</span>}
          </dd>
        </div>
      ))}
      <div className="mt-0.5 flex items-baseline gap-3 border-t border-border-subtle pt-0.5">
        <dt className="flex-1 font-medium text-foreground">Score for this step</dt>
        <dd className={cn("m-0 shrink-0 font-mono font-semibold tabular-nums", TEXT_TONE[scoreTone(reward.total)])}>{signed(reward.total)}</dd>
      </div>
    </dl>
  );
}

/** A short explanation of where the scores come from, closed until asked for. */
export function ScoringExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2 text-[12px]">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="cursor-pointer text-[11.5px] font-medium text-dim underline decoration-border underline-offset-4 hover:text-foreground">
        {open ? "Hide how scoring works" : "How scoring works"}
      </button>
      {open && <HowScoringWorks />}
    </div>
  );
}

function HowScoringWorks() {
  return (
    <div className="mt-2.5 space-y-2.5 border-t border-border-subtle pt-2.5 text-[12px] leading-relaxed text-muted-foreground">
      <p className="m-0">Scores run from <b className="text-foreground">−1</b> (bad) to <b className="text-foreground">+1</b> (good). Each step&apos;s score is built in three moves.</p>
      <ol className="m-0 list-decimal space-y-2 pl-5">
        <li>
          <b className="text-foreground">Start from the standard points.</b> Every step has a label saying what it is, and each label has fixed points.
          Work costs a little: a lookup <Mono>−0.03</Mono>, a question to the user <Mono>−0.05</Mono>, a lookup that errors <Mono>−0.13</Mono>.
          Answers are worth a lot, depending on how the user reacted: confirmed <Mono>+1.00</Mono>, no reaction <Mono>+0.30</Mono>, not found <Mono>−0.20</Mono>, rejected <Mono>−1.00</Mono>.
        </li>
        <li>
          <b className="text-foreground">Apply a quality check.</b> A grading model answers one question about the step, chosen by its label, and that moves the points a little.
          A lookup whose result was used later becomes free; one that was never used costs more.
          An answer nobody reacted to is checked against the tool results. Hover a <span className="text-sky-700 dark:text-sky-300">Quality check</span> line to see the question and the option picked.
        </li>
        <li>
          <b className="text-foreground">Pass blame or credit back.</b> When the user reacts to an answer, part of that answer&apos;s points is passed back
          to the steps that led to it: about a quarter to the step just before, a fifth to the one before that, and less and less further back.
          A rejected answer gives its steps <span className="text-red-600 dark:text-red-400">blame</span>; a confirmed one gives them <span className="text-emerald-700 dark:text-emerald-300">credit</span>.
        </li>
      </ol>
      <p className="m-0">
        The <b className="text-foreground">score for the task</b> at the top is simpler: the final answer&apos;s points plus the cost of all the work.
        Numbers are rounded to two decimals. Quality-check points are rarely round because the grading model says how likely each option is, and the points blend the options accordingly.
      </p>
    </div>
  );
}

function Mono({ children }: { children: string }) {
  return <span className="font-mono text-foreground tabular-nums">{children}</span>;
}
