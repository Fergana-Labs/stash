"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { EmptyState, Field, RmPage, StatusBadge, isActiveJob } from "@/components/reward-models/rm-ui";
import { errorMessage, formatScore, relativeTime } from "@/components/reward-models/rm-text";
import { rmCreateGepaRun, rmListGepaRuns, rmListRewardModels } from "@/lib/api";
import type { RmGepaRun, RmRewardModel } from "@/lib/types";

const POLL_MS = 3000;
const TASK_MODEL_SUGGESTIONS = ["anthropic/claude-haiku-4-5", "anthropic/claude-sonnet-5", "openai/gpt-4.1-mini", "openai/<your-vllm-model>"];
const DEFAULT_TASK_MODEL = "anthropic/claude-haiku-4-5";
const DEFAULT_REFLECTION_MODEL = "anthropic/claude-sonnet-5";
const DEFAULT_MAX_METRIC_CALLS = 150;

export default function GepaRunsPage() {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models" }, { label: "Prompt optimization" }], "rm-gepa");
  const [runs, setRuns] = useState<RmGepaRun[] | null>(null);
  const [models, setModels] = useState<RmRewardModel[] | null>(null);

  const load = useCallback(async () => {
    try {
      setRuns(await rmListGepaRuns());
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    rmListRewardModels()
      .then(setModels)
      .catch((e) => toast.error(errorMessage(e)));
  }, [load]);

  const polling = runs?.some((r) => isActiveJob(r.status)) ?? false;
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  const modelName = new Map((models ?? []).map((m) => [m.id, m.name]));

  return (
    <RmPage
      title="Prompt optimization"
      description="GEPA rewrites your agent's system prompt. Each candidate is scored by a trained reward model, and annotators' comments are the feedback for the next rewrite."
    >
      <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-8">
        <section>
          {runs === null ? (
            <RmListSkeleton />
          ) : runs.length === 0 ? (
            <EmptyState title="No optimization runs yet">Train a reward model, then optimize a prompt against it.</EmptyState>
          ) : (
            <div className="flex flex-col gap-2">
              {runs.map((run) => (
                <RunRow key={run.id} run={run} modelName={modelName.get(run.reward_model_id)} />
              ))}
            </div>
          )}
        </section>
        <OptimizeForm models={models} onCreated={() => void load()} />
      </div>
    </RmPage>
  );
}

function RunRow({ run, modelName }: { run: RmGepaRun; modelName: string | undefined }) {
  return (
    <Link
      href={`/reward-models/gepa/${run.id}`}
      className="group block rounded-lg border border-border bg-background px-4 py-3 transition-shadow hover:shadow-sm"
    >
      <div className="flex items-center gap-2.5">
        <StatusBadge status={run.status} />
        <span className="truncate font-mono text-[12.5px] text-foreground">{run.task_model}</span>
        <span className="flex-1" />
        {run.seed_score !== null && run.best_score !== null && (
          <span className="font-mono text-[12.5px] tabular-nums">
            <span className="text-muted-foreground">{formatScore(run.seed_score)}</span>
            <ArrowRight className="mx-1 inline h-3 w-3 text-muted-foreground" />
            <span className="font-semibold text-foreground">{formatScore(run.best_score)}</span>
          </span>
        )}
        <span className="text-[11.5px] text-muted-foreground">{relativeTime(run.created_at)}</span>
      </div>
      <p className="m-0 mt-1.5 line-clamp-2 text-[12.5px] leading-snug text-dim">{run.seed_prompt}</p>
      <div className="mt-1.5 text-[11.5px] text-muted-foreground">
        scored by {modelName ?? run.reward_model_id} · reflection {run.reflection_model}
      </div>
      {run.status === "failed" && run.error && (
        <div className="mt-1.5 line-clamp-2 font-mono text-[11.5px] text-red-600">{run.error}</div>
      )}
    </Link>
  );
}

function OptimizeForm({ models, onCreated }: { models: RmRewardModel[] | null; onCreated: () => void }) {
  const ready = (models ?? []).filter((m) => m.status === "succeeded");
  const [rewardModelId, setRewardModelId] = useState("");
  const [seedPrompt, setSeedPrompt] = useState("");
  const [taskModel, setTaskModel] = useState(DEFAULT_TASK_MODEL);
  const [apiBase, setApiBase] = useState("");
  const [reflectionModel, setReflectionModel] = useState(DEFAULT_REFLECTION_MODEL);
  const [maxMetricCalls, setMaxMetricCalls] = useState(DEFAULT_MAX_METRIC_CALLS);
  const [submitting, setSubmitting] = useState(false);

  const selectedId = rewardModelId === "" && ready.length > 0 ? ready[0].id : rewardModelId;

  async function submit() {
    setSubmitting(true);
    try {
      await rmCreateGepaRun({
        reward_model_id: selectedId,
        seed_prompt: seedPrompt,
        task_model: taskModel.trim(),
        ...(apiBase.trim() !== "" && { task_api_base: apiBase.trim() }),
        reflection_model: reflectionModel.trim(),
        max_metric_calls: maxMetricCalls,
      });
      onCreated();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = selectedId !== "" && seedPrompt.trim() !== "" && taskModel.trim() !== "" && reflectionModel.trim() !== "";

  return (
    <form
      className="sticky top-4 rounded-lg border border-border bg-surface/50 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 className="m-0 mb-3 text-[14px] font-semibold text-foreground">Optimize prompt</h2>
      <div className="flex flex-col gap-3">
        <Field
          label="Reward model"
          hint={
            models !== null && ready.length === 0 ? (
              <>
                No trained models yet. <Link href="/reward-models/models" className="underline">Train one first.</Link>
              </>
            ) : undefined
          }
        >
          <Select
            value={selectedId}
            onChange={setRewardModelId}
            options={ready.map((m) => ({ value: m.id, label: m.name }))}
            disabled={ready.length === 0}
            aria-label="Reward model"
            className="h-8 w-full px-2.5 text-[13px]"
          />
        </Field>
        <Field label="Seed system prompt">
          <Textarea
            value={seedPrompt}
            onChange={(e) => setSeedPrompt(e.target.value)}
            placeholder="You are a support agent for…"
            className="field-sizing-fixed h-36 resize-y font-mono text-[12px] leading-relaxed md:text-[12px]"
            required
          />
        </Field>
        <Field label="Task model" hint="Any LiteLLM model string. Use openai/<model> with an API base for vLLM, SGLang, or any OpenAI-compatible server.">
          <Input
            value={taskModel}
            onChange={(e) => setTaskModel(e.target.value)}
            list="rm-task-models"
            className="font-mono text-[12.5px] md:text-[12.5px]"
            required
          />
          <datalist id="rm-task-models">
            {TASK_MODEL_SUGGESTIONS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>
        <Field label="API base (optional)">
          <Input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="http://localhost:8000/v1"
            className="font-mono text-[12.5px] md:text-[12.5px]"
          />
        </Field>
        <Field label="Reflection model">
          <Input
            value={reflectionModel}
            onChange={(e) => setReflectionModel(e.target.value)}
            className="font-mono text-[12.5px] md:text-[12.5px]"
            required
          />
        </Field>
        <Field label="Max metric calls" hint="Budget of reward-model evaluations across all candidates.">
          <Input type="number" min={1} value={maxMetricCalls} onChange={(e) => setMaxMetricCalls(Number(e.target.value))} required />
        </Field>
        <Button type="submit" disabled={submitting || !canSubmit}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitting ? "Queuing…" : "Optimize"}
        </Button>
      </div>
    </form>
  );
}
