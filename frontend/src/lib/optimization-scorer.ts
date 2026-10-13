import type { OptimizationDetail } from "./optimization-api";

/** Name of what scores runs, for copy that used to assume a reward model. */
export function scorerName(p: Pick<OptimizationDetail, "reward_model" | "eval">): string {
  return p.eval ? `the “${p.eval.name}” eval (v${p.eval.version})` : p.reward_model?.name ?? "the reward model";
}
/** What one run's reward means. */
export function rewardMeaning(p: Pick<OptimizationDetail, "eval">): string {
  return p.eval ? `probability the eval decides “${p.eval.target_label}”` : "mean action credit per run";
}
