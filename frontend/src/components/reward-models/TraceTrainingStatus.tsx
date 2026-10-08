import Link from "next/link";
import { Check, LoaderCircle, CircleAlert } from "lucide-react";
import type { RmTraceDetail } from "@/lib/types";

export default function TraceTrainingStatus({ models }: { models: NonNullable<RmTraceDetail["training_models"]> }) {
  const model = models[0];
  if (!model) return null;
  const busy = model.status === "running" || model.status === "queued";
  const label = model.status === "succeeded" ? "Model ready" : model.status === "running" ? "Training model…" : model.status === "queued" ? "Model created" : "Training needs attention";
  const Icon = busy ? LoaderCircle : model.status === "succeeded" ? Check : CircleAlert;
  return <Link href={`/reward-models/models#model-${model.id}`} title={`${model.name}: ${label}${model.error ? ` — ${model.error}` : ""}`} aria-label={`${model.name}: ${label}`} className="inline-flex items-center gap-1 rounded-md bg-brand-500/10 px-2 py-1 text-[11px] text-brand-700 dark:text-brand-300">
    <Icon className={`size-3 ${busy ? "animate-spin motion-reduce:animate-none" : ""}`} /><span className="hidden xl:inline">{label}</span>
  </Link>;
}
