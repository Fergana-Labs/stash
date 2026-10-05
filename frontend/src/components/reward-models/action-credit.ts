import type { RmTraceDetail } from "@/lib/types";

/** Color intensity tracks distance from the training reference midpoint. */
export function creditColor(credit: number, alpha = 1): string {
  const strength = Math.min(1, Math.abs(credit));
  return `hsla(${credit < 0 ? 0 : 160}, ${15 + strength * 60}%, 43%, ${alpha})`;
}

export function formatCredit(credit: number): string {
  return `${credit >= 0 ? "+" : ""}${credit.toFixed(2)}`;
}
/** The API orders saved scores by model completion time, newest first. */
export function actionModelId(trace: Pick<RmTraceDetail, "default_evaluator" | "action_scores">, selected: string | null): string | null {
  if (selected !== "default") return selected;
  return trace.default_evaluator?.id ?? trace.action_scores?.[0]?.reward_model_id ?? null;
}
