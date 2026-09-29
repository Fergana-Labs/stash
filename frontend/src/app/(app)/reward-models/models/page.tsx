"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { EmptyState, Field, RmPage, StatusBadge, isActiveJob } from "@/components/reward-models/rm-ui";
import { errorMessage, formatSeconds, relativeTime } from "@/components/reward-models/rm-text";
import { rmCreateRewardModel, rmDownloadWeights, rmListRewardModels, rmListTraces } from "@/lib/api";
import type { RmCompute, RmRewardModel } from "@/lib/types";

const POLL_MS = 3000;
const DEFAULT_BASE_MODEL = "Qwen/Qwen3-0.6B";
const BASE_MODEL_SUGGESTIONS = ["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "HuggingFaceTB/SmolLM2-360M-Instruct"];
const TRACE_PAGE = 200;

interface LabelCounts {
  positive: number;
  negative: number;
  flagged: number;
}

/** Sums + / − labels across every page of traces. The server already leaves flagged labels out of these counts. */
async function countLabels(): Promise<LabelCounts> {
  const counts = { positive: 0, negative: 0, flagged: 0 };
  for (let offset = 0; ; offset += TRACE_PAGE) {
    const page = await rmListTraces(TRACE_PAGE, offset);
    for (const t of page.traces) {
      counts.positive += t.positive_count;
      counts.negative += t.negative_count;
      counts.flagged += t.label_error_count;
    }
    if (offset + TRACE_PAGE >= page.total) return counts;
  }
}

export default function RewardModelsPage() {
  useBreadcrumbs([{ label: "Reward models", href: "/reward-models" }, { label: "Models" }], "rm-models");
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  const [labels, setLabels] = useState<LabelCounts | null>(null);

  const load = useCallback(async () => {
    try {
      setModels(await rmListRewardModels());
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
    countLabels()
      .then(setLabels)
      .catch((e) => toast.error(errorMessage(e)));
  }, [load]);

  const polling = models?.some((m) => isActiveJob(m.status)) ?? false;
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

  return (
    <RmPage
      title="Reward models"
      description="Train a Bradley–Terry reward model on preference pairs built from your + / − labels. After training, every trace is scored."
    >
      <div className="grid grid-cols-[minmax(0,1fr)_320px] items-start gap-8">
        <section>
          {models === null ? (
            <RmListSkeleton />
          ) : models.length === 0 ? (
            <EmptyState title="No reward models yet">Label some traces with + and −, then train your first model.</EmptyState>
          ) : (
            <div className="flex flex-col gap-2.5">
              {models.map((m) => (
                <ModelCard key={m.id} model={m} />
              ))}
            </div>
          )}
        </section>
        <TrainForm labels={labels} onCreated={() => void load()} />
      </div>
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
        {model.status === "succeeded" && <DownloadWeightsButton modelId={model.id} />}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[11.5px] text-muted-foreground">
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
        <pre className="m-0 mt-3 max-h-40 overflow-auto rounded-md border border-red-500/25 bg-red-500/8 px-3 py-2 font-mono text-[12px] whitespace-pre-wrap text-red-600">
          {model.error}
        </pre>
      )}
    </div>
  );
}

function DownloadWeightsButton({ modelId }: { modelId: string }) {
  const [downloading, setDownloading] = useState(false);

  async function download() {
    setDownloading(true);
    try {
      const { blob, filename } = await rmDownloadWeights(modelId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
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

function TrainForm({ labels, onCreated }: { labels: LabelCounts | null; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [baseModel, setBaseModel] = useState(DEFAULT_BASE_MODEL);
  const [compute, setCompute] = useState<RmCompute>("local");
  const [epochs, setEpochs] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setSubmitting(true);
    try {
      await rmCreateRewardModel({ name: name.trim(), base_model: baseModel.trim(), compute, epochs });
      setName("");
      onCreated();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  }

  const missingLabels = labels !== null && (labels.positive === 0 || labels.negative === 0);

  return (
    <form
      className="sticky top-4 rounded-lg border border-border bg-surface/50 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <h2 className="m-0 mb-3 text-[14px] font-semibold text-foreground">Train reward model</h2>

      <div className="mb-4 rounded-md border border-border-subtle bg-background px-3 py-2 text-[12px]">
        {labels === null ? (
          <span className="text-muted-foreground">Counting labels…</span>
        ) : (
          <>
            <div className="flex gap-3 font-mono tabular-nums">
              <span className="text-green-700 dark:text-green-400">+{labels.positive}</span>
              <span className="text-red-600 dark:text-red-400">−{labels.negative}</span>
              <span className="text-muted-foreground">labels will train</span>
            </div>
            {labels.flagged > 0 && (
              <div className="mt-0.5 text-[11.5px] text-muted-foreground">
                {labels.flagged} flagged label{labels.flagged === 1 ? "" : "s"} excluded
              </div>
            )}
          </>
        )}
      </div>

      {missingLabels && (
        <div className="mb-4 flex gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] leading-snug text-amber-800 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Training needs at least one + and one − label. The job will fail without both.
        </div>
      )}

      <div className="flex flex-col gap-3">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="support-bot-rm-v1" required />
        </Field>
        <Field label="Base model" hint="Any Hugging Face model that loads with AutoModelForSequenceClassification.">
          <Input
            value={baseModel}
            onChange={(e) => setBaseModel(e.target.value)}
            list="rm-base-models"
            className="font-mono text-[12.5px] md:text-[12.5px]"
            required
          />
          <datalist id="rm-base-models">
            {BASE_MODEL_SUGGESTIONS.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Compute">
            <Select
              value={compute}
              onChange={(v) => setCompute(v as RmCompute)}
              options={[
                { value: "local", label: "Local" },
                { value: "modal", label: "Modal GPU" },
              ]}
              aria-label="Compute"
              className="h-8 w-full px-2.5 text-[13px]"
            />
          </Field>
          <Field label="Epochs">
            <Input type="number" min={1} max={20} value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} required />
          </Field>
        </div>
        <p className="m-0 text-[11.5px] leading-snug text-muted-foreground">
          {compute === "local"
            ? "Runs on this server: Apple MPS, CUDA when present, else CPU."
            : "Runs the same code on a Modal A10G."}
        </p>
        <Button type="submit" disabled={submitting || name.trim() === "" || baseModel.trim() === ""}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitting ? "Queuing…" : "Train reward model"}
        </Button>
      </div>
    </form>
  );
}
