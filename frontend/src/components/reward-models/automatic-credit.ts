import type { RmActionScore, RmStep } from "@/lib/types";
import type { TraceEvaluationResponse } from "@/lib/workbench-api";

function normalizedCredit(credit: NonNullable<TraceEvaluationResponse["current"]>["credits"][number]) {
  // Support older backend instances during deployment; an explicit null is authoritative.
  return credit.expected_credit === undefined ? (credit.credit === null ? null : credit.credit / 2) : credit.expected_credit;
}

/** Match the automatic classifier's action eligibility, excluding context events. */
export function isGradableAction(step: RmStep) {
  return step.role === "assistant" && !step.metadata?.thinking && Boolean(step.tool_name || step.content?.trim());
}

/** Earlier annotations are display-only; the current evaluation remains authoritative. */
export function automaticActionScores(evaluation: TraceEvaluationResponse | null, steps: RmStep[]) {
  const scores = new Map<string, RmActionScore>();
  const visible = new Set(steps.map((step) => step.id));
  const current = evaluation?.current;
  const previous = current?.status === "completed" ? [] : evaluation?.previous_credits ?? [];
  for (const credit of previous) {
    const value = normalizedCredit(credit);
    if (value === null || !visible.has(credit.step_id)) continue;
    scores.set(credit.step_id, {
      step_id: credit.step_id, score: value, credit: value,
      reward_model_id: "automatic", reward_model_name: "Automatic annotation",
      created_at: credit.created_at, stale: true,
    });
  }
  for (const credit of current?.credits ?? []) {
    // An explicit uncertain result supersedes an earlier numeric annotation too.
    scores.delete(credit.step_id);
    const value = normalizedCredit(credit);
    if (value === null || !visible.has(credit.step_id)) continue;
    scores.set(credit.step_id, {
      step_id: credit.step_id, score: value, credit: value,
      reward_model_id: "automatic", reward_model_name: "Automatic annotation",
      created_at: current!.created_at,
    });
  }
  return scores;
}

export function automaticAnnotationProgress(evaluation: TraceEvaluationResponse | null, steps: RmStep[], scores: Map<string, RmActionScore>) {
  const actions = steps.filter(isGradableAction);
  const current = evaluation?.current;
  const credits = new Map([
    ...(current?.status === "completed" ? [] : evaluation?.previous_credits ?? []),
    ...current?.credits ?? [],
  ].map((credit) => [credit.step_id, credit]));
  const unscoredReasons = new Map<string, string>();
  let uncertain = 0;
  let previous = 0;
  let scored = 0;
  for (const action of actions) {
    const score = scores.get(action.id);
    if (score) {
      scored++;
      if (score.stale) previous++;
    } else if (credits.has(action.id) && normalizedCredit(credits.get(action.id)!) === null) {
      uncertain++;
      unscoredReasons.set(action.id, "insufficient evidence");
    } else {
      unscoredReasons.set(action.id, "awaiting score");
    }
  }
  const pending = actions.length - scored - uncertain;
  const parts = [`${scored} of ${actions.length} actions scored`];
  if (previous) parts.push(`${previous} previous`);
  if (pending) parts.push(`${pending} awaiting scores`);
  if (uncertain) parts.push(`${uncertain} with insufficient evidence`);
  const queue = evaluation?.queue;
  if (!evaluation) parts.push("Loading annotations…");
  else if (!evaluation.configured) parts.push("Automatic annotation unavailable");
  else if (queue?.status === "failed") parts.push("Annotation update failed");
  else if (queue?.status === "waiting" || (!evaluation.boundary && current?.status !== "completed")) parts.push("Waiting for response completion");
  else if (queue?.status === "queued" && queue.error) parts.push("Retrying annotation update…");
  else if (current?.status !== "completed") parts.push("Updating annotations…");
  return { label: parts.join(" · "), unscoredReasons };
}
