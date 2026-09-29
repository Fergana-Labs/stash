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
// Same rules the server enforces on skill_name / skill_description.
const SKILL_NAME_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const SKILL_NAME_MAX = 64;
const SKILL_DESCRIPTION_MAX = 1024;

export default function GepaRunsPage() {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models" }, { label: "Skills" }], "rm-gepa");
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
      title="Skills"
      description="GEPA writes a skill for your agent: a SKILL.md it loads into context. Each draft is scored by a trained reward model, and annotators' comments are the feedback for the next draft."
    >
      <div className="grid grid-cols-[minmax(0,1fr)_360px] items-start gap-8">
        <section>
          {runs === null ? (
            <RmListSkeleton />
          ) : runs.length === 0 ? (
            <EmptyState title="No skills yet">Train a reward model, then create a skill scored by it.</EmptyState>
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
        <span className="truncate font-mono text-[13px] font-medium text-foreground">{run.skill_name}</span>
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
      <p className="m-0 mt-1.5 line-clamp-2 text-[12.5px] leading-snug text-dim">{run.skill_description}</p>
      <div className="mt-1.5 text-[11.5px] text-muted-foreground">
        scored by {modelName ?? run.reward_model_id} · task {run.task_model} · reflection {run.reflection_model}
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
  const [skillName, setSkillName] = useState("");
  const [description, setDescription] = useState("");
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
        skill_name: skillName,
        skill_description: description.trim(),
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

  const nameValid = SKILL_NAME_PATTERN.test(skillName) && skillName.length <= SKILL_NAME_MAX;
  const descriptionLength = description.trim().length;
  const descriptionValid = descriptionLength >= 1 && descriptionLength <= SKILL_DESCRIPTION_MAX;
  const canSubmit =
    selectedId !== "" && nameValid && descriptionValid && taskModel.trim() !== "" && reflectionModel.trim() !== "";

  return (
    <form
      className="sticky top-4 rounded-lg border border-border bg-surface/50 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 className="m-0 mb-3 text-[14px] font-semibold text-foreground">Create a skill</h2>
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
        <Field
          label="Skill name"
          hint={
            skillName !== "" && !nameValid ? (
              <span className="text-red-600">Lowercase letters, digits, and single hyphens; up to 64 characters.</span>
            ) : (
              "e.g. refund-requests"
            )
          }
        >
          <Input
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            placeholder="refund-requests"
            maxLength={SKILL_NAME_MAX}
            aria-invalid={skillName !== "" && !nameValid}
            className="font-mono text-[12.5px] md:text-[12.5px]"
            required
          />
        </Field>
        <Field
          label="Description"
          hint={
            <span className="flex justify-between gap-2">
              <span>When should the agent use this skill?</span>
              <span className="tabular-nums">
                {descriptionLength}/{SKILL_DESCRIPTION_MAX}
              </span>
            </span>
          }
        >
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Use when a customer asks for a refund, return, or replacement."
            maxLength={SKILL_DESCRIPTION_MAX}
            className="field-sizing-fixed h-24 resize-y text-[13px] leading-snug md:text-[13px]"
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
        <Field label="Max metric calls" hint="Budget of reward-model evaluations across all skill drafts.">
          <Input type="number" min={1} value={maxMetricCalls} onChange={(e) => setMaxMetricCalls(Number(e.target.value))} required />
        </Field>
        <Button type="submit" disabled={submitting || !canSubmit}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitting ? "Queuing…" : "Create skill"}
        </Button>
      </div>
    </form>
  );
}
