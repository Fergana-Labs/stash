"use client";

import { useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import type { RmActionScore, RmStep, RmTraceDetail } from "@/lib/types";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import { isContextGroup } from "./trace-outline";
import { presentTrace } from "./trace-presentation";
import { rowSteps, type TraceRow } from "./trace-rows";

/** Use the same message, Markdown and tool rendering as the main trace viewer. */
export default function ModelTraceConversation({ trace, scores, modelName, feedback }: {
  trace: RmTraceDetail; scores: RmActionScore[]; modelName: string; feedback?: (step: RmStep, number: number) => ReactNode;
}) {
  const anchorPrefix = useId();
  const [choices, setChoices] = useState<Map<string, boolean>>(new Map());
  const { rows, numberById } = presentTrace(trace.steps);
  const expanded = (row: TraceRow) => choices.get(row.key) ?? false;
  const rowByStep = new Map(rows.flatMap((row) => rowSteps(row).map((step) => [step.id, row] as const)));
  const groups: { context: boolean; rows: TraceRow[] }[] = [];
  for (const row of rows) {
    const context = isContextGroup({ key: row.key, rows: [row], children: [] });
    const previous = groups.at(-1);
    if (previous?.context === context) previous.rows.push(row);
    else groups.push({ context, rows: [row] });
  }
  const scoreByStep = new Map(scores.map((score) => [score.step_id, score]));
  const ann: StepAnnotations = {
    anchorId: (step) => `model-trace-${anchorPrefix}-${step.id}`,
    stepNumber: (step) => numberById.get(step.id),
    actionScore: (step) => scoreByStep.get(step.id),
    actionScoreSource: modelName,
    highlights: () => [], commentCount: () => 0, hasQuotes: () => false, flashing: () => false,
    onSelectAnnotation: () => {},
    footer: feedback ? (step) => {
      const row = rowByStep.get(step.id);
      return row && expanded(row) ? feedback(step, numberById.get(step.id) ?? step.index + 1) : null;
    } : undefined,
  };
  return <div data-trace-scroll className="scroll-thin max-h-[min(52vh,420px)] space-y-1 overflow-auto overscroll-contain border-y border-border py-2" aria-label={scores.length ? "Graded conversation" : "Trace conversation"}>
    {groups.map((group) => {
      const timeline = <TraceTimeline rows={group.rows} taskRows={rows} ann={ann} isExpanded={expanded} onToggle={(row) => setChoices((previous) => new Map(previous).set(row.key, !expanded(row)))} />;
      const first = numberById.get(rowSteps(group.rows[0])[0].id);
      const last = numberById.get(rowSteps(group.rows.at(-1)!)[0].id);
      return group.context ? <details key={group.rows[0].key} className="group/context rounded-sm bg-surface/60">
        <summary className="flex h-7 cursor-pointer list-none items-center gap-2 px-3 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden"><ChevronRight className="size-3.5 transition-transform group-open/context:rotate-90" /><span>Context</span><span className="ml-auto text-[11px] tabular-nums">{first === last ? first : `${first}–${last}`}</span></summary>
        {timeline}
      </details> : <div key={group.rows[0].key}>{timeline}</div>;
    })}
  </div>;
}
