"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { rmListRewardModels, rmScoreTrace } from "@/lib/api";
import type { RmRewardModel, RmTraceDetail } from "@/lib/types";
import { errorMessage } from "./rm-text";

export default function ActionScoringPanel({ trace, selectedModelId, onModelChange, onReload }: {
  trace: RmTraceDetail;
  selectedModelId: string | null;
  onModelChange: (id: string | null) => void;
  onReload: () => Promise<void>;
}) {
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void rmListRewardModels().then((all) => {
      if (cancelled) return;
      const eligible = all.filter((m) => m.status === "succeeded" && m.metrics?.action_scoring_version === 1);
      setModels(eligible);
      onModelChange(eligible[0]?.id ?? null);
    }).catch((e) => { if (!cancelled) setLoadError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [onModelChange]);

  const run = trace.scoring_runs?.find((r) => r.reward_model_id === selectedModelId);
  const active = run?.status === "queued" || run?.status === "running";
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void onReload(), 3000);
    return () => clearInterval(timer);
  }, [active, onReload]);

  const eligible = trace.steps.filter((s) => s.role === "assistant" && (s.tool_name || s.content.trim()));
  const scored = trace.action_scores?.filter((s) => s.reward_model_id === selectedModelId).length ?? 0;
  async function score() {
    if (!selectedModelId) return;
    setRequesting(true);
    try {
      await rmScoreTrace(trace.id, selectedModelId);
      await onReload();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setRequesting(false);
    }
  }

  return (
    <section aria-label="Action credit" className="mb-4 rounded-md border border-border px-3 py-2.5 text-[12px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Action credit</span>
        {models !== null && models.length > 0 && (
          <>
            <select aria-label="Action credit model" value={selectedModelId ?? ""} onChange={(e) => onModelChange(e.target.value || null)}
              className="min-w-0 max-w-64 rounded border border-border bg-background px-2 py-1">
              <option value="">Hide scores</option>
              {models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            {selectedModelId && <>
              <span className="text-muted-foreground">{scored} / {eligible.length} actions scored</span>
              <button type="button" onClick={() => void score()} disabled={requesting || active || !eligible.length}
                className="ml-auto cursor-pointer rounded border border-border px-2 py-1 hover:bg-surface disabled:cursor-default disabled:opacity-50">
                {requesting || active ? "Scoring…" : scored ? "Score again" : "Score actions"}
              </button>
            </>}
          </>
        )}
      </div>
      {loadError ? <p role="alert" className="mt-2 text-red-600">Could not load reward models: {loadError}</p>
        : models === null ? <p className="mt-2 text-muted-foreground">Loading reward models…</p>
        : models.length === 0 ? <p className="mt-2 text-muted-foreground"><Link className="underline" href="/reward-models">Train a reward model</Link> with action comparisons to highlight tool calls and responses. Older models need new training.</p>
        : selectedModelId && <p className="mt-2 text-muted-foreground">Learned reward from −1 to +1. Higher means this model prefers the action in context; zero is the training reference midpoint. These scores are not correctness probabilities or contributions that add up to the trace score.</p>}
      {selectedModelId && run?.status === "failed" && <p role="alert" className="mt-2 text-red-600">Scoring failed: {run.error ?? "Please try again."}</p>}
    </section>
  );
}
