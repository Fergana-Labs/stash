"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import CreateModelDialog from "@/components/intuitions/CreateModelDialog";
import LoadExampleButton from "@/components/intuitions/LoadExampleButton";
import { pct } from "@/components/intuitions/im-helpers";
import { Callout, LoadError } from "@/components/intuitions/im-ui";
import { imList, type JudgeStatus, type ModelSummary } from "@/lib/intuition-api";

export default function IntuitionsPage() {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models" }, { label: "Intuitions" }], "im-list");
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [judge, setJudge] = useState<JudgeStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await imList();
      setModels(res.models);
      setJudge(res.judge);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <RmPage
      title="Intuition models"
      description="Personal judges that learn your taste. Each one asks the Jev judge a rubric of questions and combines the answers with small, editable weights fitted to your examples."
      actions={
        models !== null && models.length > 0 ? (
          <>
            <LoadExampleButton />
            <Button onClick={() => setCreating(true)}>
              <Plus /> New intuition model
            </Button>
          </>
        ) : undefined
      }
    >
      <CreateModelDialog open={creating} onOpenChange={setCreating} />
      {judge && !judge.configured && (
        <div className="mb-4">
          <Callout tone="warning">
            Jev is not configured: set <code className="font-mono">TYPESAFE_API_KEY</code>. You can still explore the bundled example, which is pre-graded.
          </Callout>
        </div>
      )}
      {loadError !== null ? (
        <LoadError what="intuition models" message={loadError} onRetry={() => void load()} />
      ) : models === null ? (
        <RmListSkeleton />
      ) : models.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-surface/40 px-6 py-12 text-center">
          <p className="m-0 text-[14px] font-medium text-foreground">No intuition models yet</p>
          <p className="mx-auto mt-1.5 max-w-lg text-[12.5px] leading-relaxed text-muted-foreground">
            An intuition model turns your judgment calls into a reusable judge your agents can ask. You write a few questions that capture what you look for, label examples, and it learns how much each answer matters to you.
          </p>
          <div className="mt-4 flex justify-center gap-2">
            <LoadExampleButton />
            <Button onClick={() => setCreating(true)}>
              <Plus /> New intuition model
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-2.5 md:grid-cols-2">
          {models.map((m) => (
            <ModelCard key={m.id} model={m} />
          ))}
        </div>
      )}
    </RmPage>
  );
}

function ModelCard({ model }: { model: ModelSummary }) {
  const evalMetrics = model.active_metrics?.eval;
  const blurb = model.draft_description ?? model.active_description ?? "";
  return (
    <Link
      href={`/reward-models/intuitions/${model.id}`}
      className="group block rounded-lg border border-border bg-background px-4 py-3 transition-colors hover:border-brand-300 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-foreground group-hover:text-brand-600">{model.name}</span>
        {model.inbox > 0 && (
          <span className="tag tag-brand" title={`${model.inbox} predictions to review`}>
            {model.inbox} to review
          </span>
        )}
      </div>
      {blurb && <p className="m-0 mt-1 line-clamp-2 text-[12px] leading-snug text-muted-foreground">{blurb}</p>}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground">
        <span className="tag tag-muted">{model.output_type}</span>
        <span className="font-mono">{model.active_number != null ? `v${model.active_number} active` : "not promoted"}</span>
        {model.draft_version_id && <span className="tag tag-warning">draft</span>}
        <span>
          <span className="font-mono text-foreground">{pct(evalMetrics?.accuracy)}</span> held-out
          {evalMetrics && evalMetrics.n > 0 && <span className="font-mono"> (n={evalMetrics.n})</span>}
        </span>
        <span>
          <span className="font-mono">{model.examples}</span> examples
        </span>
        <span className="ml-auto">{relativeTime(model.updated_at)}</span>
      </div>
    </Link>
  );
}
