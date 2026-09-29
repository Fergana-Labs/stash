"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { EmptyState, RmPage, StatusBadge, isActiveJob, pendingSkillTitle } from "@/components/reward-models/rm-ui";
import { errorSummary, errorMessage, formatScore, relativeTime } from "@/components/reward-models/rm-text";
import { rmListGepaRuns, rmListRewardModels } from "@/lib/api";
import type { RmGepaRun, RmRewardModel } from "@/lib/types";

const POLL_MS = 3000;

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

  return (
    <RmPage
      title="Skills"
      description="GEPA writes a skill for your agent: a SKILL.md it loads into context. Each draft is scored by a trained reward model, and annotators' comments are the feedback for the next draft."
    >
      {runs === null || models === null ? (
        <RmListSkeleton />
      ) : runs.length === 0 ? (
        <EmptyState title="No skills yet">
          Train a reward model, then press{" "}
          <Link href="/reward-models/models" className="underline">
            Create skill
          </Link>{" "}
          on it.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-2">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} model={models.find((m) => m.id === run.reward_model_id)!} />
          ))}
        </div>
      )}
    </RmPage>
  );
}

function RunRow({ run, model }: { run: RmGepaRun; model: RmRewardModel }) {
  return (
    <Link
      href={`/reward-models/gepa/${run.id}`}
      className="group block rounded-lg border border-border bg-background px-4 py-3 transition-shadow hover:shadow-sm"
    >
      <div className="flex items-center gap-2.5">
        <StatusBadge status={run.status} />
        {run.skill_name !== null ? (
          <span className="truncate font-mono text-[13px] font-medium text-foreground">{run.skill_name}</span>
        ) : (
          <span className="truncate text-[13px] text-muted-foreground">{pendingSkillTitle(run.status)}</span>
        )}
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
      {run.skill_description !== null && (
        <p className="m-0 mt-1.5 line-clamp-2 text-[12.5px] leading-snug text-dim">{run.skill_description}</p>
      )}
      <div className="mt-1.5 text-[11.5px] text-muted-foreground">from reward model {model.name}</div>
      {run.status === "failed" && run.error && (
        <div className="mt-1.5 line-clamp-2 font-mono text-[11.5px] text-muted-foreground">{errorSummary(run.error)}</div>
      )}
    </Link>
  );
}
