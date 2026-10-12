import type { RmRewardModel } from "@/lib/types";

export function trainingStage(model: RmRewardModel): string {
  if (model.status !== "running") return { queued: "Queued", succeeded: "Ready", failed: "Failed" }[model.status];
  switch (model.progress?.stage) {
    case "preparing": return "Preparing data";
    case "starting": return model.compute === "modal" ? "Starting GPU" : "Starting";
    case "loading": return "Loading model";
    case "evaluating": return "Evaluating";
    case "scoring": return "Scoring traces";
    case "uploading": return "Uploading";
    default: return "Training";
  }
}

function durationRange(lower: number, upper: number) {
  if (upper < 60) return "<1m";
  const low = Math.max(1, Math.round(lower / 60));
  const high = Math.max(low, Math.ceil(upper / 60));
  return low === high ? `≈${high}m` : `≈${low}–${high}m`;
}

function TimingText({ model }: { model: RmRewardModel }) {
  if (model.status !== "queued" && model.status !== "running") return <span>—</span>;
  const timing = model.estimated_timing;
  const since = new Date(model.started_at ?? model.created_at).toLocaleTimeString();
  const elapsedHint = `${model.status === "queued" ? "Queued" : "Started"} at ${since}.`;
  if (!timing) {
    const hint = model.status === "queued"
      ? "Waiting for a worker. An estimate appears once there is comparable run history or live batch timing."
      : "Collecting timing data. An estimate appears when enough batches have completed; model loading and final checks can vary.";
    return <span title={`${elapsedHint} ${hint}`}>Estimating…</span>;
  }
  const basis = timing.basis === "history"
    ? `Based on ${timing.sample_count} comparable completed run${timing.sample_count === 1 ? "" : "s"}.`
    : `Based on ${timing.sample_count} completed batches. Covers training only; evaluation, scoring and upload follow.`;
  const title = `${elapsedHint} ${basis}${timing.excludes_queue ? " Queue wait is additional and cannot yet be estimated." : ""}`;
  if (timing.overdue) return <span title={`${title} This run has exceeded its estimated range.`}>Taking longer…</span>;
  return <span title={title}>
    {durationRange(timing.lower_seconds, timing.upper_seconds)}
    {timing.excludes_queue ? " + queue" : timing.scope === "training" ? " training" : ""}
  </span>;
}

export default function ModelTiming({ model }: { model: RmRewardModel }) {
  if (model.status !== "queued" && model.status !== "running") return <span>—</span>;
  const progress = model.progress;
  const measured = model.status === "running" && progress?.stage === "training" && progress.total > 0;
  const percentage = measured ? Math.min(100, Math.max(0, progress.completed / progress.total * 100)) : undefined;
  return <div className="flex min-w-24 flex-col gap-1.5">
    <TimingText model={model} />
    <div role="progressbar" aria-label="Training progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage} aria-valuetext={measured ? `${progress.completed} of ${progress.total} training batches` : trainingStage(model)} className="h-1 w-24 overflow-hidden rounded-full bg-border">
      <div className={percentage === undefined ? "h-full w-1/3 animate-pulse rounded-full bg-brand-500 motion-reduce:animate-none" : "h-full rounded-full bg-brand-500 transition-[width] motion-reduce:transition-none"} style={percentage === undefined ? undefined : { width: `${percentage}%` }} />
    </div>
  </div>;
}
