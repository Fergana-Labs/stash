// Design from Priyadarshan's trace viewer (projects/trace_viewer)
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { RmTraceDetail } from "@/lib/types";
import { formatScore, relativeTime } from "./rm-text";

/** The aside's Overview block: counts at a glance and the latest score from each reward model. */
export default function TraceOverview({ trace }: { trace: RmTraceDetail }) {
  const live = trace.annotations.filter((a) => !a.label_error);
  const toolCalls = trace.steps.filter((s) => s.role === "assistant" && s.tool_name !== null).length;
  const turns = trace.steps.filter((s) => s.role === "user").length;

  return (
    <section className="rounded-xl border border-border bg-background px-4 py-3.5">
      <h3 className="sys-label m-0 mb-2.5">Overview</h3>
      <div className="grid grid-cols-3 gap-x-3 gap-y-3">
        <Mini label="steps" value={trace.steps.length} />
        <Mini label="turns" value={turns} />
        <Mini label="tool calls" value={toolCalls} />
        <Mini label="good (+)" value={live.filter((a) => a.rating === 1).length} tone="positive" />
        <Mini label="bad (−)" value={live.filter((a) => a.rating === -1).length} tone="negative" />
        <Mini label="flagged" value={trace.annotations.length - live.length} tone={trace.annotations.length > live.length ? "flagged" : undefined} />
      </div>
      {trace.scores.length > 0 && (
        <dl className="m-0 mt-4 space-y-1.5 border-t border-border-subtle pt-3 text-[12px]">
          {trace.scores.map((s) => (
            <div key={s.reward_model_id} className="flex items-baseline justify-between gap-3" title={`Scored ${relativeTime(s.created_at)}`}>
              <dt className="min-w-0 truncate text-muted-foreground">{s.reward_model_name}</dt>
              <dd className="m-0 font-mono text-[13px] font-medium text-foreground tabular-nums">{formatScore(s.score)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

const TONE: Record<"positive" | "negative" | "flagged", string> = {
  positive: "text-green-700 dark:text-green-400",
  negative: "text-red-600 dark:text-red-400",
  flagged: "text-amber-600",
};

function Mini({ label, value, tone }: { label: string; value: ReactNode; tone?: keyof typeof TONE }) {
  return (
    <div>
      <div className={cn("font-display text-[21px] leading-none tabular-nums", tone && value !== 0 ? TONE[tone] : "text-foreground")}>{value}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}
