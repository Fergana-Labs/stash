import type { RmTraceSummary } from "@/lib/types";

export function traceScore(trace: RmTraceSummary): number | null {
  return trace.evaluation?.current ? trace.evaluation.score ?? null : null;
}

export function traceScoreLabel(): string {
  return "Automatic trace annotation: the mean of the task scores, from −1 (bad) to +1 (good)";
}

export function traceCredits(trace: RmTraceSummary) {
  return trace.evaluation?.current ? trace.evaluation.action_credit : null;
}
