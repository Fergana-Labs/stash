"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import ViewSkillButton from "@/components/reward-models/ViewSkillButton";
import FeedbackDialog from "@/components/reward-models/FeedbackDialog";
import TrainSheet from "@/components/reward-models/TrainSheet";
import { SELECTED_PARAM } from "@/components/reward-models/trace-selection";
import { EmptyState, RmPage, StatusBadge, isActiveJob } from "@/components/reward-models/rm-ui";
import { errorMessage, formatSeconds, relativeTime } from "@/components/reward-models/rm-text";
import { JobError } from "@/components/reward-models/JobError";
import { rmDownloadWeights, rmGetRewardModel, rmListRewardModels } from "@/lib/api";
import type { RmRewardModel } from "@/lib/types";

const POLL_MS = 3000;

export default function RewardModelsPage() {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models" }, { label: "Models" }], "rm-models");
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setModels(await rmListRewardModels());
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const polling = loadError === null && (models?.some((m) => isActiveJob(m.status)) ?? false);
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  return (
    <RmPage
      title="Reward models"
      actions={<Button onClick={() => setSheetOpen(true)}>Create new reward model</Button>}
    >
      <TrainSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onTrained={() => {
          setSheetOpen(false);
          void load();
        }}
      />
      {loadError !== null ? (
        <div role="alert" className="py-6 text-sm">
          <p className="font-medium">Couldn’t load reward models.</p>
          <p className="mt-1 text-muted-foreground">{loadError}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : models === null ? (
        <RmListSkeleton />
      ) : models.length === 0 ? (
        <EmptyState title="No reward models yet">Create a model to learn from feedback in your traces.</EmptyState>
      ) : (
        <div className="flex flex-col gap-2.5">
          {models.map((m) => (
            <ModelCard key={m.id} model={m} />
          ))}
        </div>
      )}
    </RmPage>
  );
}

function ModelCard({ model }: { model: RmRewardModel }) {
  const metrics = model.metrics;
  return (
    <div className="rounded-lg border border-border bg-background px-4 py-3">
      <div className="flex items-center gap-2.5">
        <span className="truncate text-[14px] font-medium text-foreground">{model.name}</span>
        <StatusBadge status={model.status} />
        <span className="flex-1" />
        <span className="text-[11.5px] text-muted-foreground">{relativeTime(model.created_at)}</span>
        {!isActiveJob(model.status) && <FeedbackDialog modelId={model.id} />}
        {model.status === "succeeded" && (
          <>
            <DownloadWeightsButton modelId={model.id} />
            <ViewSkillButton modelId={model.id} />
          </>
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 font-mono text-[11.5px] text-muted-foreground">
        <TrainedOnLink model={model} />
        <span>{model.base_model}</span>
        <span>{model.compute}</span>
        <span>
          {model.epochs} epoch{model.epochs === 1 ? "" : "s"}
        </span>
      </div>

      {metrics && (
        <dl className="m-0 mt-3 grid grid-cols-4 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle">
          <Metric label="Eval accuracy" value={`${(metrics.eval_accuracy * 100).toFixed(1)}%`} emphasis />
          <Metric label="Pairs" value={`${metrics.train_pairs} + ${metrics.eval_pairs}`} hint="train + held-out" />
          <Metric label="Device" value={metrics.device} />
          <Metric label="Time" value={formatSeconds(metrics.seconds)} hint={`loss ${metrics.final_loss.toFixed(3)}`} />
        </dl>
      )}

      {model.status === "failed" && model.error && (
        <JobError error={model.error} className="mt-3" />
      )}
    </div>
  );
}

/** "Trained on N traces" opens the Traces tab with exactly those traces selected. */
function TrainedOnLink({ model }: { model: RmRewardModel }) {
  const router = useRouter();
  const [opening, setOpening] = useState(false);

  async function open() {
    setOpening(true);
    try {
      const detail = await rmGetRewardModel(model.id);
      router.push(`/reward-models?${SELECTED_PARAM}=${detail.trace_ids.join(",")}`);
    } catch (e) {
      toast.error(errorMessage(e));
      setOpening(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void open()}
      disabled={opening}
      className="inline-flex cursor-pointer items-center gap-1 font-sans text-[12px] text-dim underline decoration-border underline-offset-2 hover:text-brand-600 hover:decoration-brand-300 disabled:cursor-wait"
    >
      {opening && <Loader2 className="h-3 w-3 animate-spin" />}
      Trained on {model.trace_count} trace{model.trace_count === 1 ? "" : "s"}
    </button>
  );
}

function DownloadWeightsButton({ modelId }: { modelId: string }) {
  const [downloading, setDownloading] = useState(false);

  async function download() {
    setDownloading(true);
    try {
      const { url } = await rmDownloadWeights(modelId);
      const link = document.createElement("a");
      link.href = url;
      link.click();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Button variant="outline" size="xs" onClick={() => void download()} disabled={downloading}>
      {downloading ? <Loader2 className="animate-spin" /> : <Download />}
      {downloading ? "Downloading…" : "Download weights"}
    </Button>
  );
}

function Metric({ label, value, hint, emphasis }: { label: string; value: string; hint?: string; emphasis?: boolean }) {
  return (
    <div className="bg-surface/60 px-3 py-2">
      <dt className="text-[10.5px] tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className={`m-0 mt-0.5 font-mono tabular-nums ${emphasis ? "text-[16px] font-semibold text-foreground" : "text-[13px] text-foreground"}`}>
        {value}
      </dd>
      {hint && <div className="text-[10.5px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
