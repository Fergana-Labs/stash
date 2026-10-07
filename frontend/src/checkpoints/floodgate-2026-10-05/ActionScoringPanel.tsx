"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { rmListRewardModels, rmScoreTrace, rmSetTrainingContribution } from "@/lib/api";
import type { RmRewardModel, RmTraceDetail } from "@/lib/types";
import { errorMessage } from "@/components/reward-models/rm-text";

export default function ActionScoringPanel({ trace, selectedModelId, onModelChange, onReload }: {
  trace: RmTraceDetail;
  selectedModelId: string | null;
  onModelChange: (id: string | null) => void;
  onReload: () => Promise<void>;
}) {
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [savingConsent, setSavingConsent] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void rmListRewardModels().then((all) => {
      if (cancelled) return;
      const eligible = all.filter((m) => m.status === "succeeded" && m.metrics?.action_scoring_version === 1);
      setModels(eligible);
    }).catch((e) => { if (!cancelled) setLoadError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, []);

  const isDefault = selectedModelId === "default";
  const effectiveModelId = isDefault ? trace.default_evaluator?.id : selectedModelId;
  const eligible = trace.steps.filter((s) => s.role === "assistant" && (s.tool_name || s.content.trim()));
  const run = trace.scoring_runs?.find((r) => r.reward_model_id === effectiveModelId);
  const active = run?.status === "queued" || run?.status === "running";
  const pending = isDefault && !!trace.default_evaluator && !!eligible.length && !!trace.automatic_scoring && trace.automatic_scoring.attempts < 3;
  useEffect(() => {
    if (!active && !pending) return;
    const timer = setInterval(() => void onReload(), 3000);
    return () => clearInterval(timer);
  }, [active, pending, onReload]);

  const scored = trace.action_scores?.filter((s) => s.reward_model_id === effectiveModelId).length ?? 0;
  async function score() {
    if (!effectiveModelId) return;
    setRequesting(true);
    try {
      await rmScoreTrace(trace.id, isDefault ? undefined : effectiveModelId);
      await onReload();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setRequesting(false);
    }
  }

  async function contribute(allowed: boolean) {
    setSavingConsent(true);
    try {
      await rmSetTrainingContribution(trace.id, allowed);
      await onReload();
    } catch (e) { toast.error(errorMessage(e)); }
    finally { setSavingConsent(false); }
  }

  return (
    <section aria-label="Action credit" className="mb-4 rounded-md border border-border px-3 py-2.5 text-[12px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Action credit</span>
        {isDefault && <span className="text-muted-foreground">{trace.default_evaluator ? `Stash evaluator · v${trace.default_evaluator.revision}` : "Stash evaluator"}</span>}
        {effectiveModelId && <>
          <span className="text-muted-foreground">{scored} / {eligible.length} actions scored</span>
          <button type="button" onClick={() => void score()} disabled={requesting || active || !eligible.length}
            className="ml-auto cursor-pointer rounded border border-border px-2 py-1 hover:bg-surface disabled:cursor-default disabled:opacity-50">
            {requesting || active ? "Scoring…" : scored ? "Score again" : "Score actions"}
          </button>
        </>}
      </div>
      {isDefault && !trace.default_evaluator && <p className="mt-2 text-muted-foreground">Waiting for the first Stash evaluator release. This trace will be scored automatically when it is available.</p>}
      {pending && !active && <p className="mt-2 text-muted-foreground">Automatic scoring is queued.</p>}
      {effectiveModelId && <p className="mt-2 text-muted-foreground">Learned reward from −1 to +1. Higher means this model prefers the action in context; zero is the training reference midpoint. These scores are not correctness probabilities or contributions that add up to the trace score. Use Comment on an action to correct its assessment.</p>}
      {effectiveModelId && run?.status === "failed" && <p role="alert" className="mt-2 text-red-600">Scoring failed: {run.error ?? "Please try again."}{pending ? " Retrying automatically." : ""}</p>}
      <label className="mt-3 flex items-start gap-2">
        <input type="checkbox" checked={trace.shared_training_allowed ?? false} disabled={savingConsent}
          onChange={(e) => void contribute(e.target.checked)} className="mt-0.5" />
        Allow this trace and its feedback to improve Stash’s shared evaluator
      </label>
      {trace.shared_training_allowed && <p className="mt-1 text-muted-foreground">Corrections and independently reviewed comparisons contribute to future training. Turning this off removes the contribution from future candidates; it does not remove what released models have already learned.</p>}
      {trace.shared_training_allowed && trace.training_collection?.status === "failed" && <p role="alert" className="mt-1 text-red-600">Feedback collection failed: {trace.training_collection.error}</p>}
      <details className="mt-2 text-muted-foreground">
        <summary className="cursor-pointer">Advanced: personal reward models</summary>
        <select aria-label="Action credit model" value={selectedModelId ?? ""} onChange={(e) => onModelChange(e.target.value || null)}
          className="mt-2 min-w-0 max-w-64 rounded border border-border bg-background px-2 py-1">
          <option value="default">Stash evaluator (automatic)</option>
          <option value="">Hide scores</option>
          {(models ?? []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
        {loadError && <p role="alert" className="mt-1 text-red-600">Could not load personal models: {loadError}</p>}
        <p className="mt-1"><Link className="underline" href="/reward-models">Train a reward model</Link> for a custom rubric. Older models need new training to score actions.</p>
      </details>
    </section>
  );
}
