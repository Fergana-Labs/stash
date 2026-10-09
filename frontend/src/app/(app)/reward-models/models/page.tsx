"use client";

import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, ChevronRight, Download, Loader2, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import ViewSkillButton from "@/components/reward-models/ViewSkillButton";
import FeedbackDialog from "@/components/reward-models/FeedbackDialog";
import TrainSheet from "@/components/reward-models/TrainSheet";
import { SELECTED_PARAM } from "@/components/reward-models/trace-selection";
import { isActiveJob } from "@/components/reward-models/rm-ui";
import { errorMessage, formatSeconds } from "@/components/reward-models/rm-text";
import { JobError } from "@/components/reward-models/JobError";
import { rmDownloadWeights, rmGetRewardModel, rmListRewardModels } from "@/lib/api";
import type { RmJobStatus, RmRewardModel } from "@/lib/types";
import { cn } from "@/lib/utils";

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
    <div className="scroll-thin h-full overflow-y-auto px-6 pt-5 pb-12">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h1 className="m-0 font-display text-[18px] font-semibold tracking-tight text-foreground">Reward models</h1>
        <Button size="sm" onClick={() => setSheetOpen(true)}><Plus />New model</Button>
      </div>
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
      ) : (
        <ModelTable models={models ?? []} loading={models === null} />
      )}
    </div>
  );
}

const STATUS_LABEL: Record<RmJobStatus, string> = { queued: "Queued", running: "Training", succeeded: "Ready", failed: "Failed" };

function ModelTable({ models, loading }: { models: RmRewardModel[]; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<{ key: "name" | "created"; ascending: boolean }>({ key: "created", ascending: false });
  const needle = query.trim().toLowerCase();
  const visible = models.filter((m) => (status === "all" || m.status === status)
    && `${m.name} ${m.base_model}`.toLowerCase().includes(needle)).sort((a, b) => {
    const order = sort.key === "name" ? a.name.localeCompare(b.name) : Date.parse(a.created_at) - Date.parse(b.created_at);
    return sort.ascending ? order : -order;
  });

  function sortBy(key: "name" | "created") {
    setSort((previous) => ({ key, ascending: previous.key === key ? !previous.ascending : key === "name" }));
  }
  const SortIcon = sort.ascending ? ArrowUp : ArrowDown;

  return <>
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <label className="flex h-7 w-56 items-center gap-1.5 rounded-md border border-border px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20">
        <Search className="size-3.5 text-muted-foreground" />
        <input aria-label="Search models" placeholder="Search models…" value={query} onChange={(e) => setQuery(e.target.value)} disabled={loading} className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-muted-foreground" />
      </label>
      <Select aria-label="Filter model status" value={status} onChange={setStatus} disabled={loading} className="h-7 min-w-28 px-2 text-[12px]" options={[
        { value: "all", label: "All statuses" }, ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })),
      ]} />
      {!loading && <span className="ml-auto text-[12px] text-muted-foreground tabular-nums">{visible.length === models.length ? `${models.length} model${models.length === 1 ? "" : "s"}` : `${visible.length} of ${models.length} models`}</span>}
    </div>
    <div className="overflow-x-auto border-y border-border">
      <table aria-label="Reward models" className="w-full min-w-[900px] table-fixed border-collapse text-left text-[12.5px] text-foreground">
        <colgroup><col /><col className="w-24" /><col className="w-44" /><col className="w-16" /><col className="w-28" /><col className="w-48" /></colgroup>
        <thead className="border-b border-border bg-surface/60 text-[11.5px] text-muted-foreground">
          <tr className="h-7 [&>th]:px-3 [&>th]:py-0 [&>th]:font-medium">
            <th scope="col" aria-sort={sort.key === "name" ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button type="button" onClick={() => sortBy("name")} className="flex cursor-pointer items-center gap-1 hover:text-foreground">Model{sort.key === "name" && <SortIcon className="size-3" />}</button>
            </th>
            <th scope="col">Status</th><th scope="col">Base model</th><th scope="col" className="text-right">Traces</th><th scope="col" className="text-right">Eval accuracy</th>
            <th scope="col" aria-sort={sort.key === "created" ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button type="button" onClick={() => sortBy("created")} className="ml-auto flex cursor-pointer items-center gap-1 hover:text-foreground">Created{sort.key === "created" && <SortIcon className="size-3" />}</button>
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((model) => <ModelRow key={model.id} model={model} />)}
          {loading && <tr><td colSpan={6} className="px-3 py-5 text-muted-foreground"><span role="status">Loading reward models…</span></td></tr>}
          {!loading && visible.length === 0 && <tr><td colSpan={6} className="px-3 py-5">
            <p className="m-0 font-medium text-foreground">{models.length === 0 ? "No reward models yet" : "No matching models"}</p>
            <p className="m-0 mt-1 text-[12px] text-muted-foreground">{models.length === 0 ? "Create a model from your traces to start training." : "Try another name or status."}</p>
            {models.length > 0 && <Button variant="ghost" size="xs" className="mt-2 -ml-2" onClick={() => { setQuery(""); setStatus("all"); }}>Clear filters</Button>}
          </td></tr>}
        </tbody>
      </table>
    </div>
  </>;
}

function ModelRow({ model }: { model: RmRewardModel }) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    let frame = 0;
    const reveal = () => {
      if (window.location.hash !== `#model-${model.id}`) return;
      frame = requestAnimationFrame(() => {
        setExpanded(true);
        document.getElementById(`model-${model.id}`)?.scrollIntoView({ block: "nearest" });
      });
    };
    reveal();
    window.addEventListener("hashchange", reveal);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("hashchange", reveal); };
  }, [model.id]);
  const metrics = model.metrics;
  const detailsId = `model-details-${model.id}`;
  const date = new Date(model.created_at);
  const timestamp = date.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });
  return (
    <Fragment>
      <tr id={`model-${model.id}`} data-model-row className={cn("h-8 scroll-mt-4 border-b border-border-subtle last:border-0 hover:bg-surface/60 focus-within:bg-surface/60 target:bg-brand-500/5 [&>td]:px-3 [&>td]:py-0", expanded && "bg-surface/60")}>
        <td>
          <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls={detailsId} className="flex h-7 w-full cursor-pointer items-center gap-2 text-left font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50" title={model.name}>
            <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground", expanded && "rotate-90")} /><span className="truncate">{model.name}</span>
          </button>
        </td>
        <td><span className="inline-flex items-center gap-1.5 text-[12px]">
          {isActiveJob(model.status) ? <Loader2 className="size-3 animate-spin text-muted-foreground motion-reduce:animate-none" /> : <span className={cn("size-1.5 rounded-full", model.status === "succeeded" ? "bg-emerald-600/70 dark:bg-emerald-400/70" : "bg-red-500")} />}
          {STATUS_LABEL[model.status]}
        </span></td>
        <td className="text-muted-foreground"><span className="block truncate" title={model.base_model}>{model.base_model}</span></td>
        <td className="text-right tabular-nums">{model.trace_count}</td>
        <td className="text-right tabular-nums">{metrics?.eval_accuracy == null ? <span className="text-muted-foreground">—</span> : `${(metrics.eval_accuracy * 100).toFixed(1)}%`}</td>
        <td className="text-right text-[11.5px] text-muted-foreground tabular-nums"><time dateTime={model.created_at} title={date.toLocaleString(undefined, { timeZoneName: "long" })}>{timestamp}</time></td>
      </tr>
      {expanded && <tr><td colSpan={6} className="border-b border-border px-8 py-3">
        <div id={detailsId} role="region" aria-label={`${model.name} details`}>
          <div className="flex flex-wrap items-center gap-2">
            <TrainedOnLink model={model} />
            <span className="ml-1 text-[12px] text-muted-foreground">{model.compute} · {model.epochs} epoch{model.epochs === 1 ? "" : "s"}</span>
            <span className="flex-1" />
            {!isActiveJob(model.status) && <FeedbackDialog modelId={model.id} />}
            {model.status === "succeeded" && (
              <>
                <DownloadWeightsButton modelId={model.id} />
                <ViewSkillButton modelId={model.id} />
              </>
            )}
          </div>
          {metrics && (
            <dl className="m-0 mt-3 flex flex-wrap gap-x-8 gap-y-3 border-t border-border-subtle pt-3">
              <Metric label="Eval accuracy" value={metrics.eval_accuracy == null ? "Not available" : `${(metrics.eval_accuracy * 100).toFixed(1)}%`} hint={metrics.eval_split === "trace" ? "held-out traces" : undefined} />
              <Metric label="Pairs" value={`${metrics.train_pairs} + ${metrics.eval_pairs}`} hint="train + held-out" />
              <Metric label="Device" value={metrics.device} />
              <Metric label="Time" value={formatSeconds(metrics.seconds)} hint={`loss ${metrics.final_loss.toFixed(3)}`} />
              {metrics.action_scoring_version === 1 && <>
                <Metric label="Action accuracy" value={metrics.action_eval_accuracy == null ? "Not available" : `${(metrics.action_eval_accuracy * 100).toFixed(1)}%`} hint={`${metrics.action_eval_pairs ?? 0} held-out action pairs`} />
                <Metric label="Tool-call accuracy" value={metrics.tool_eval_accuracy == null ? "Not available" : `${(metrics.tool_eval_accuracy * 100).toFixed(1)}%`} hint={`${metrics.tool_eval_pairs ?? 0} held-out tool pairs`} />
              </>}
            </dl>
          )}

          {model.status === "failed" && model.error && (
            <JobError error={model.error} className="mt-3" />
          )}
        </div>
      </td></tr>}
    </Fragment>
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

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-[11px] text-muted-foreground">{label}</dt>
      <dd className="m-0 mt-0.5 text-[13px] text-foreground tabular-nums">
        {value}
      </dd>
      {hint && <div className="text-[10.5px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
