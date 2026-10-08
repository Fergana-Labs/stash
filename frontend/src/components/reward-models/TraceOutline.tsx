"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { StepLabelChips } from "./StepLabels";
import { PointsChip, TaskScoreChip } from "./StepRewards";
import TraceTimeline, { type StepAnnotations } from "./TraceTimeline";
import { signed } from "./step-rewards";
import type { OutlineTask, OutlineTurn } from "./trace-outline";
import type { TraceRow } from "./trace-rows";

/**
 * The trace as tasks, then turns, then steps. Each level shows a one-line
 * summary and opens to the next, so a long trace reads top-down and the
 * detail only appears where the reader goes looking for it.
 */
export default function TraceOutline({ tasks, isOpen, onToggleGroup, showLabels, showScores, inView, ann, isExpanded, onToggle, onJump }: {
  tasks: OutlineTask[];
  isOpen: (key: string) => boolean;
  onToggleGroup: (key: string) => void;
  showLabels: boolean;
  showScores: boolean;
  inView: (row: TraceRow) => boolean;
  ann: StepAnnotations;
  isExpanded: (row: TraceRow) => boolean;
  onToggle: (row: TraceRow) => void;
  onJump: (stepId: string) => void;
}) {
  return (
    <div className="space-y-3 pt-2">
      {tasks.map((task) => {
        const open = isOpen(task.key);
        return (
          <section key={task.key} aria-label={`Task ${task.number}`} className="rounded-lg border border-border-subtle">
            <GroupHeader open={open} onToggle={() => onToggleGroup(task.key)} className="px-3 py-2.5">
              <span className="shrink-0 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">Task {task.number}</span>
              <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-foreground" title={task.title}>{task.title}</span>
              {showLabels && <StepLabelChips chips={task.answerChips} onJump={onJump} className="shrink-0 flex-nowrap" />}
              {showScores && task.score && <TaskScoreChip score={task.score} />}
              <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">{task.turns.length === 1 ? "1 turn" : `${task.turns.length} turns`} · {task.steps} steps</span>
            </GroupHeader>
            {open && (
              <div className="border-t border-border-subtle">
                {showScores && task.score && (
                  <p className="m-0 border-b border-border-subtle px-3 py-1.5 text-[11.5px] text-muted-foreground">
                    {task.score.hasAnswer ? "The final answer earned" : "No answer was given, so that part is"}{" "}
                    <span className="font-mono text-foreground tabular-nums">{signed(task.score.answer ?? 0)}</span> and the work to get there cost{" "}
                    <span className="font-mono text-foreground tabular-nums">{signed(task.score.costs)}</span>
                    {Math.abs((task.score.answer ?? 0) + task.score.costs - task.score.score) > 0.005 ? ", which is capped to the −1 to +1 range." : "."}
                  </p>
                )}
                {task.turns.map((turn) => (
                  <Turn key={turn.key} turn={turn} showLabels={showLabels} showScores={showScores} open={isOpen(turn.key)} onToggleGroup={onToggleGroup} inView={inView} ann={ann} isExpanded={isExpanded} onToggle={onToggle} onJump={onJump} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function Turn({ turn, showLabels, showScores, open, onToggleGroup, inView, ann, isExpanded, onToggle, onJump }: {
  turn: OutlineTurn;
  showLabels: boolean;
  showScores: boolean;
  open: boolean;
  onToggleGroup: (key: string) => void;
  inView: (row: TraceRow) => boolean;
  ann: StepAnnotations;
  isExpanded: (row: TraceRow) => boolean;
  onToggle: (row: TraceRow) => void;
  onJump: (stepId: string) => void;
}) {
  const rows = turn.rows.filter(inView);
  return (
    <div className="border-b border-border-subtle last:border-b-0">
      <GroupHeader open={open} onToggle={() => onToggleGroup(turn.key)} className="px-3 py-2">
        <span className="shrink-0 text-[12px] font-semibold text-foreground">{turn.prompt ? "User" : "Setup"}</span>
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-foreground/80" title={turn.preview}>{turn.preview}</span>
        {showLabels && <StepLabelChips chips={turn.userChips} onJump={onJump} className="shrink-0 flex-nowrap" />}
        {(turn.work !== "" || turn.answerChips.length > 0) && <span aria-hidden="true" className="shrink-0 text-muted-foreground">→</span>}
        {turn.work !== "" && <span className="shrink-0 text-[11.5px] text-muted-foreground">{turn.work}</span>}
        {showLabels && <StepLabelChips chips={turn.answerChips.slice(0, 1)} onJump={onJump} className="shrink-0 flex-nowrap" />}
        {showScores && turn.points !== null && <PointsChip points={turn.points} title="The scores of the steps in this turn, added up." />}
      </GroupHeader>
      {open && (
        <div className="px-3 pb-1">
          <TraceTimeline rows={rows} ann={ann} isExpanded={isExpanded} onToggle={onToggle} />
          {rows.length === 0 && <p className="m-0 py-3 text-[12px] text-muted-foreground">No steps in this view.</p>}
        </div>
      )}
    </div>
  );
}

function GroupHeader({ open, onToggle, className, children }: { open: boolean; onToggle: () => void; className?: string; children: React.ReactNode }) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={open}
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onToggle();
        }
      }}
      className={cn("flex cursor-pointer items-center gap-2.5 select-none hover:bg-surface/60", className)}
    >
      <ChevronRight aria-hidden="true" className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
      {children}
    </div>
  );
}
