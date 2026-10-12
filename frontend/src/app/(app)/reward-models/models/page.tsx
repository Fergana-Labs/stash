"use client";

import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState, type MouseEvent } from "react";
import { ArrowDown, ArrowUp, ChevronRight, Loader2, Plus, Search } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import TrainSheet from "@/components/reward-models/TrainSheet";
import { isActiveJob } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import ModelTiming, { trainingStage } from "@/components/reward-models/ModelTiming";
import { rmListRewardModels } from "@/lib/api";
import type { RmJobStatus, RmRewardModel } from "@/lib/types";
import { cn } from "@/lib/utils";

import ModelPlayground from "@/components/reward-models/ModelPlayground";
import TraceModelConnect from "@/components/reward-models/TraceModelConnect";
import IntuitionDetail from "@/components/intuitions/IntuitionDetail";
import LoadExampleButton from "@/components/intuitions/LoadExampleButton";
import { imList, type ModelSummary } from "@/lib/intuition-api";

const POLL_MS = 3000;

export default function RewardModelsPage() {
  useBreadcrumbs([{ label: "Reward models" }], "rm-models");
  const router = useRouter();
  const [models, setModels] = useState<RmRewardModel[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rubricLoadError, setRubricLoadError] = useState<string | null>(null);
  const [rubricModels, setRubricModels] = useState<ModelSummary[]>([]);
  const [judgeConfigured, setJudgeConfigured] = useState(true);
  const [sheetOpen, setSheetOpen] = useState(false);

  const load = useCallback(async () => {
    setLoadError(null); setRubricLoadError(null);
    await Promise.all([
      rmListRewardModels().then(setModels).catch((e) => setLoadError(errorMessage(e))),
      imList().then((rubric) => {
        setRubricModels(rubric.models);
        setJudgeConfigured(rubric.judge.configured);
      }).catch((e) => setRubricLoadError(errorMessage(e))),
    ]);
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
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu modal={false}><DropdownMenuTrigger asChild><Button size="sm" variant="ghost" className="text-muted-foreground">More options</Button></DropdownMenuTrigger><DropdownMenuContent align="end"><LoadExampleButton asMenuItem /></DropdownMenuContent></DropdownMenu>
          <Button size="sm" onClick={() => setSheetOpen(true)}><Plus />New model</Button>
        </div>
      </div>
      {rubricLoadError && <p role="alert" className="mb-4 text-xs text-muted-foreground">Couldn’t load rubric-based models: {rubricLoadError}. <button className="cursor-pointer underline" onClick={() => void load()}>Retry rubric models</button></p>}
      {!judgeConfigured && <p className="mb-4 text-xs text-muted-foreground">Live rubric-based predictions are unavailable until the judge is connected. Load the example to explore the sandbox with recorded results.</p>}
      <TrainSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        onTrained={(model) => {
          setSheetOpen(false);
          router.push(`/reward-models/models/${model.id}`);
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
        <>
          <ModelTable models={models ?? []} rubricModels={rubricModels} loading={models === null} />
          {models && models.length > 0 && <div className="mt-4 border-t border-border"><TraceModelConnect modelId={models[0].id} models={models.map((model) => ({ value: model.id, label: model.name }))} /></div>}
        </>
      )}
    </div>
  );
}

const STATUS_LABEL: Record<RmJobStatus, string> = { queued: "Queued", running: "Training", succeeded: "Ready", failed: "Failed" };

function ModelTable({ models: trainedModels, rubricModels, loading }: { models: RmRewardModel[]; rubricModels: ModelSummary[]; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState<{ key: "name" | "created"; ascending: boolean }>({ key: "created", ascending: false });
  const models = [
    ...trainedModels.map((model) => ({ ...model, kind: "trained" as const, rubric: null })),
    ...rubricModels.map((model) => ({
      id: model.id, name: model.name, base_model: "Rubric-based",
      status: model.active_number === null ? "draft" as const : "succeeded" as const,
      created_at: model.created_at, kind: "rubric" as const, rubric: model,
    })),
  ];
  const needle = query.trim().toLowerCase();
  const visible = models.filter((m) => (status === "all" || m.status === status)
    && `${m.name} ${m.base_model} ${m.rubric?.active_description ?? m.rubric?.draft_description ?? ""}`.toLowerCase().includes(needle)).sort((a, b) => {
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
        { value: "all", label: "All statuses" }, { value: "draft", label: "Draft" }, ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })),
      ]} />
      {!loading && <span className="ml-auto text-[12px] text-muted-foreground tabular-nums">{visible.length === models.length ? `${models.length} model${models.length === 1 ? "" : "s"}` : `${visible.length} of ${models.length} models`}</span>}
    </div>
    <div className="overflow-x-auto border-y border-border">
      <table aria-label="Reward models" className="w-full min-w-[1080px] table-fixed border-collapse text-left text-[12.5px] text-foreground">
        <colgroup><col /><col className="w-32" /><col className="w-36" /><col className="w-44" /><col className="w-32" /><col className="w-28" /><col className="w-48" /></colgroup>
        <thead className="border-b border-border bg-surface/60 text-[11.5px] text-muted-foreground">
          <tr className="h-7 [&>th]:px-3 [&>th]:py-0 [&>th]:font-medium">
            <th scope="col" aria-sort={sort.key === "name" ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button type="button" onClick={() => sortBy("name")} className="flex cursor-pointer items-center gap-1 hover:text-foreground">Model{sort.key === "name" && <SortIcon className="size-3" />}</button>
            </th>
            <th scope="col">Status</th><th scope="col">Est. remaining</th><th scope="col">Model type / base</th><th scope="col" className="whitespace-nowrap text-right">Examples / traces</th><th scope="col" className="text-right">Eval accuracy</th>
            <th scope="col" aria-sort={sort.key === "created" ? sort.ascending ? "ascending" : "descending" : "none"}>
              <button type="button" onClick={() => sortBy("created")} className="ml-auto flex cursor-pointer items-center gap-1 hover:text-foreground">Created{sort.key === "created" && <SortIcon className="size-3" />}</button>
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((model) => model.kind === "rubric" ? <RubricModelRow key={`rubric-${model.id}`} model={model.rubric} /> : <ModelRow key={`trained-${model.id}`} model={model} />)}
          {loading && <tr><td colSpan={7} className="px-3 py-5 text-muted-foreground"><span role="status">Loading reward models…</span></td></tr>}
          {!loading && visible.length === 0 && <tr><td colSpan={7} className="px-3 py-5">
            <p className="m-0 font-medium text-foreground">{models.length === 0 ? "No reward models yet" : "No matching models"}</p>
            <p className="m-0 mt-1 text-[12px] text-muted-foreground">{models.length === 0 ? "Train a reward model from your traces." : "Try another name or status."}</p>
            {models.length > 0 && <Button variant="ghost" size="xs" className="mt-2 -ml-2" onClick={() => { setQuery(""); setStatus("all"); }}>Clear filters</Button>}
          </td></tr>}
        </tbody>
      </table>
    </div>
  </>;
}

function toggleFromRow(event: MouseEvent<HTMLTableRowElement>, toggle: () => void) {
  // The name and chevron retain their own keyboard-accessible handlers.
  if (event.defaultPrevented || (event.target as Element).closest("button, a, input, select, textarea, [contenteditable]")) return;
  if (window.getSelection()?.type === "Range") return;
  toggle();
}

function RubricModelRow({ model }: { model: ModelSummary }) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = `rubric-model-details-${model.id}`;
  const accuracy = model.active_metrics?.eval?.accuracy;
  return <Fragment><tr data-model-row onClick={(event) => toggleFromRow(event, () => setExpanded(!expanded))} className={cn("h-8 cursor-pointer border-b border-border-subtle last:border-0 hover:bg-surface/60 focus-within:bg-surface/60 [&>td]:px-3 [&>td]:py-0", expanded && "bg-surface/60")}>
    <td><div className="flex min-w-0 items-center gap-2">
      <button type="button" onClick={() => setExpanded(!expanded)} aria-label={`${model.name} details`} aria-expanded={expanded} aria-controls={detailsId} className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50">
        <ChevronRight className={cn("size-3.5 text-muted-foreground", expanded && "rotate-90")} />
      </button>
      <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls={detailsId} className="cursor-pointer truncate py-1 text-left font-medium hover:text-brand-600 hover:underline" title={model.name}>{model.name}</button>
    </div></td>
    <td>{model.active_number === null ? "Draft" : `Ready · v${model.active_number}`}</td>
    <td className="text-muted-foreground">—</td>
    <td className="text-muted-foreground">Rubric-based</td>
    <td className="text-right tabular-nums">{model.examples}</td>
    <td className="text-right tabular-nums">{accuracy == null ? "—" : `${(accuracy * 100).toFixed(1)}%`}</td>
    <td className="text-right text-[11.5px] text-muted-foreground"><time dateTime={model.created_at}>{new Date(model.created_at).toLocaleString()}</time></td>
  </tr>
    {expanded && <tr><td colSpan={7} className="border-b border-border p-0">
      <div id={detailsId} role="region" aria-label={model.name + " details"}>
        <IntuitionDetail id={model.id} embedded />
      </div>
    </td></tr>}
  </Fragment>;
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
      <tr id={`model-${model.id}`} data-model-row onClick={(event) => toggleFromRow(event, () => setExpanded(!expanded))} className={cn("h-8 cursor-pointer scroll-mt-4 border-b border-border-subtle last:border-0 hover:bg-surface/60 focus-within:bg-surface/60 target:bg-brand-500/5 [&>td]:px-3 [&>td]:py-0", expanded && "bg-surface/60")}>
        <td>
          <div className="flex min-w-0 items-center gap-2">
            <button type="button" onClick={() => setExpanded(!expanded)} aria-label={`${model.name} details`} aria-expanded={expanded} aria-controls={detailsId} className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50">
              <ChevronRight className={cn("size-3.5 text-muted-foreground", expanded && "rotate-90")} />
            </button>
            <button type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls={detailsId} className="cursor-pointer truncate py-1 text-left font-medium hover:text-brand-600 hover:underline" title={model.name}>{model.name}</button>
          </div>
        </td>
        <td><span className="inline-flex items-center gap-1.5 text-[12px]">
          {isActiveJob(model.status) ? <Loader2 className="size-3 animate-spin text-muted-foreground motion-reduce:animate-none" /> : <span className={cn("size-1.5 rounded-full", model.status === "succeeded" ? "bg-emerald-600/70 dark:bg-emerald-400/70" : "bg-red-500")} />}
          {trainingStage(model)}
        </span></td>
        <td className="text-[12px] text-muted-foreground tabular-nums"><ModelTiming model={model} /></td>
        <td className="text-muted-foreground"><span className="block truncate" title={`Fine-tuned · ${model.base_model}`}>Fine-tuned · {model.base_model}</span></td>
        <td className="text-right tabular-nums">{model.trace_count}</td>
        <td className="text-right tabular-nums">{metrics?.eval_accuracy == null ? <span className="text-muted-foreground">—</span> : `${(metrics.eval_accuracy * 100).toFixed(1)}%`}</td>
        <td className="text-right text-[11.5px] text-muted-foreground tabular-nums"><time dateTime={model.created_at} title={date.toLocaleString(undefined, { timeZoneName: "long" })}>{timestamp}</time></td>
      </tr>
      {expanded && <tr><td colSpan={7} className="border-b border-border p-0">
        <div id={detailsId} role="region" aria-label={model.name + " details"}>
          <ModelPlayground modelId={model.id} embedded />
        </div>
      </td></tr>}
    </Fragment>
  );
}
