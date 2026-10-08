import { LoaderCircle } from "lucide-react";
import type { TraceEvaluationResponse } from "@/lib/workbench-api";

function scoreState(evaluation: TraceEvaluationResponse | null, error: string | null) {
  const current = evaluation?.current;
  // A rule score stands on its own; the earlier policy's estimate of success needs an established outcome.
  const ruleScore = current?.outcome_probabilities?.score;
  const probability = current?.outcome !== "insufficient_evidence" ? current?.outcome_probabilities?.success : null;
  const value = ruleScore ?? probability;
  const score = typeof value === "number" && Number.isFinite(value) ? value : null;
  if (error) return { score, label: score === null ? "Couldn't load" : "Update unavailable", description: "Couldn't refresh the trace score. It will retry automatically." };
  if (score !== null) return { score, label: null, description: "Automatic trace annotation: the mean of the task scores, from −1 (bad) to +1 (good)." };
  if (!evaluation) return { score, label: "Loading…", busy: true, description: "Loading the saved trace score." };
  if (current?.outcome === "insufficient_evidence") return { score, label: "Insufficient evidence", description: "The classifier could not determine whether this trace was successful." };
  if (!evaluation.configured) return { score, label: "Unavailable", description: "Automatic trace scoring is currently unavailable." };
  const queue = evaluation.queue;
  if (queue?.status === "failed") return { score, label: "Scoring failed", description: "The scoring attempt failed. This is not a failure verdict on the trace." };
  if (queue?.status === "waiting" || !evaluation.boundary) return { score, label: "Waiting for response", description: "Scoring will begin once the agent finishes its response." };
  const recalculating = evaluation.history.some((entry) => entry.id !== current?.id && entry.outcome !== null);
  if (queue?.status === "queued") return { score, label: recalculating ? "Recalculation queued" : "Queued", description: "Waiting to score the current version of this trace." };
  if (queue?.status === "running" || current?.status === "running") return { score, label: recalculating ? "Recalculating…" : "Scoring…", busy: true, description: "Calculating the success score for the current version of this trace." };
  if (current?.status === "failed") return { score, label: "Scoring failed", description: "The scoring attempt failed. This is not a failure verdict on the trace." };
  return { score, label: "Awaiting score", description: "No success score is available for the current version of this trace yet." };
}

export default function TraceScore({ evaluation, error }: { evaluation: TraceEvaluationResponse | null; error: string | null }) {
  const state = scoreState(evaluation, error);
  return (
    <div role="status" aria-label="Trace score" title={state.description} className="mr-2 flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[10px] text-muted-foreground">Trace score</span>
      {state.score !== null && <span className="font-mono text-[16px] font-medium text-foreground tabular-nums">{state.score.toFixed(2)}</span>}
      {state.label && <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
        {state.busy && <LoaderCircle aria-hidden="true" className="size-3 animate-spin motion-reduce:animate-none" />}
        {state.label}
      </span>}
    </div>
  );
}
