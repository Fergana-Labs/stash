"use client";

import { useEffect, useState } from "react";
import type { RmScoringRun } from "@/lib/types";

const labels = {
  preparing: "Preparing trace",
  starting: "Starting GPU worker",
  downloading: "Downloading model checkpoint",
  loading: "Loading model on GPU",
  scoring: "Scoring trace",
  saving: "Saving scores",
};

function duration(seconds: number) {
  const rounded = Math.max(5, Math.ceil(seconds / 5) * 5);
  return rounded < 60 ? rounded + "s" : Math.ceil(rounded / 60) + "m";
}

export default function ScoringProgress({ run, modelName }: { run: RmScoringRun | null; modelName: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const progress = run?.progress;
  const queued = run?.status === "queued";
  const determinate = !queued && progress?.stage === "scoring" && progress.total > 0;
  const percent = determinate ? Math.min(100, Math.max(0, progress.completed / progress.total * 100)) : undefined;
  const age = progress ? (now - Date.parse(progress.updated_at)) / 1000 : NaN;
  // Startup is unmeasured. Estimate only the remaining inference work, from
  // completed batches, and stop showing the estimate if telemetry goes stale.
  const remaining = determinate && progress.completed >= 4 && progress.completed < progress.total && progress.elapsed_seconds >= 2 && age >= -1 && age <= 15
    ? progress.elapsed_seconds / progress.completed * (progress.total - progress.completed) - Math.max(0, age)
    : null;
  const started = Date.parse(run?.started_at ?? run?.created_at ?? "");
  const elapsed = Number.isFinite(started) ? Math.max(0, Math.floor((now - started) / 1000)) : null;
  const label = !run ? "Submitting scoring request" : queued ? "Queued for scoring" : progress ? labels[progress.stage] ?? "Scoring trace" : "Starting GPU worker";
  const status = queued || progress?.stage === "scoring" ? `${label} with ${modelName}…` : label + "…";
  return <div className="space-y-2 text-xs">
    <div className="flex items-center justify-between gap-3" role="status">
      <span>{status}</span>
      {determinate && <span className="shrink-0 tabular-nums text-muted-foreground">{progress.completed} / {progress.total}</span>}
    </div>
    <div role="progressbar" aria-label="Scoring progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={determinate ? `${progress.completed} of ${progress.total} items scored` : label} className="h-1.5 overflow-hidden rounded-full bg-muted">
      <div className={determinate ? "h-full rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none" : "h-full w-1/3 rounded-full bg-primary/60 motion-safe:animate-pulse"} style={determinate ? { width: percent + "%" } : undefined} />
    </div>
    {(elapsed !== null || (remaining !== null && remaining > 0)) && <div className="flex items-center justify-between gap-3 text-muted-foreground tabular-nums">
      <span>{elapsed !== null ? (elapsed < 60 ? elapsed + "s" : Math.floor(elapsed / 60) + "m " + elapsed % 60 + "s") + " elapsed" : ""}</span>
      {remaining !== null && remaining > 0 && <span>About {duration(remaining)} scoring left</span>}
    </div>}
  </div>;
}
