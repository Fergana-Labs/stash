import type { RmActionScore, RmStep } from "@/lib/types";
import type { TraceEvaluationResponse } from "@/lib/workbench-api";

/** Earlier annotations are display-only; the current evaluation remains authoritative. */
export function automaticActionScores(evaluation: TraceEvaluationResponse | null, steps: RmStep[]) {
  const scores = new Map<string, RmActionScore>();
  const visible = new Set(steps.map((step) => step.id));
  const current = evaluation?.current;
  const previous = current?.status === "completed" ? [] : evaluation?.previous_credits ?? [];
  for (const credit of previous) {
    if (credit.credit === null || !visible.has(credit.step_id)) continue;
    scores.set(credit.step_id, {
      step_id: credit.step_id, score: credit.credit, credit: credit.credit / 2,
      reward_model_id: "automatic", reward_model_name: "Automatic annotation",
      created_at: credit.created_at, stale: true,
    });
  }
  for (const credit of current?.credits ?? []) {
    // An explicit uncertain result supersedes an earlier numeric annotation too.
    scores.delete(credit.step_id);
    if (credit.credit === null || !visible.has(credit.step_id)) continue;
    scores.set(credit.step_id, {
      step_id: credit.step_id, score: credit.credit, credit: credit.credit / 2,
      reward_model_id: "automatic", reward_model_name: "Automatic annotation",
      created_at: current!.created_at,
    });
  }
  return scores;
}
