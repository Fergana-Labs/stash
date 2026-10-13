"use client";

import Link from "next/link";
import { Fragment, useCallback, useId, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { RmPage } from "@/components/reward-models/rm-ui";
import { relativeTime } from "@/components/reward-models/rm-text";
import { ErrorNotice, RecordBadge, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import CreateOptimization from "@/components/optimization/CreateOptimization";
import RollingRewardChart, { signed, value } from "@/components/monitoring/RollingRewardChart";
import PromptEvolution from "@/components/monitoring/PromptEvolution";
import GepaHistory from "@/components/monitoring/GepaHistory";
import { getOptimization } from "@/lib/optimization-api";
import { getMonitoring, getRewardHistory, type MonitoredAgent, type MonitoringOverview } from "@/lib/monitoring-api";
import { cn } from "@/lib/utils";

function AgentDetail({ agent, overview }: { agent: MonitoredAgent; overview: MonitoringOverview }) {
  const programs = overview.programs.filter((p) => p.agent === agent.agent);
  const [selectedProgram, setProgram] = useState(programs.find((p) => p.status === "active")?.id ?? programs[0]?.id ?? "recorded");
  const program = programs.find((p) => p.id === selectedProgram);
  const [selectedModel, setModel] = useState(overview.models[0]?.id ?? "");
  const modelId = program?.reward_model_id ?? selectedModel;
  const [window, setWindow] = useState(20);
  const [creating, setCreating] = useState(false);
  const selection = `${agent.agent}:${modelId}:${program?.id ?? "recorded"}:${window}`;
  const loader = useCallback(async () => ({ selection, history: modelId ? await getRewardHistory(agent.agent, modelId, window, program?.id) : null }), [selection, agent.agent, modelId, window, program?.id]);
  const { data, error, reload } = useWorkbenchLoad(loader, 10000);
  const programId = program?.id;
  const detailLoader = useCallback(async () => programId ? getOptimization(programId) : null, [programId]);
  const { data: detail, error: detailError, reload: reloadDetail } = useWorkbenchLoad(detailLoader, 10000);
  const history = data?.selection === selection ? data.history : null;
  const matchingDetail = detail?.id === program?.id ? detail : null;
  const fullWindows = history && history.current_n === window && history.previous_n === window;
  const change = fullWindows && history.current_mean != null && history.previous_mean != null ? history.current_mean - history.previous_mean : null;
  return <section aria-label={`${agent.display_name} monitoring`} className="px-6 py-4">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-center gap-3">
      {!!programs.length && <Select aria-label="Workload" value={selectedProgram} onChange={setProgram} options={[{ value: "recorded", label: "All recorded runs" }, ...programs.map((p) => ({ value: p.id, label: `${p.name} · ${p.scope}` }))]} className="h-9 max-w-lg px-3 text-xs" />}
      <Select aria-label="Reward model" value={modelId} onChange={setModel} disabled={!!program} options={[...overview.models.map((m) => ({ value: m.id, label: m.name })), ...(program && !overview.models.some((m) => m.id === program.reward_model_id) ? [{ value: program.reward_model_id, label: program.reward_model_name }] : [])]} className="h-9 min-w-48 px-3 text-xs" />
      <Select aria-label="Rolling window" value={String(window)} onChange={(s) => setWindow(Number(s))} options={[20, 50, 100].map((n) => ({ value: String(n), label: `Last ${n} scored runs` }))} className="h-9 px-3 text-xs" />
      {program && <RecordBadge value={program.status === "active" ? "optimizing" : program.status} />}
    </div><Button size="sm" variant="outline" disabled={!overview.models.length} onClick={() => setCreating(!creating)}>{creating ? "Cancel" : "Optimize prompt"}</Button></div>
    {creating && <div className="mb-5"><CreateOptimization initialModelId={modelId} initialAgent={agent.agent} /></div>}
    <ErrorNotice error={error ?? detailError} onRetry={() => { void reload(); void reloadDetail(); }} />
    {!overview.models.length && !program ? <p className="text-sm text-muted-foreground">Choose a <Link className="underline" href="/reward-models/models">reward model</Link> once it is ready to monitor agent performance.</p> : !history ? <p role="status" className="py-6 text-sm text-muted-foreground">Loading agent rewards…</p> : <>
      <div className="mb-5 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Metric label="Average reward" content={value(history.current_mean)} hint={`${history.current_n} recent scored runs${program ? ` · current prompt v${program.active_version}` : ""}`} />
        <Metric label="Change from previous window" content={change == null ? "—" : signed(change)} hint={change == null ? `Needs ${window * 2} scored runs${program ? " on the current prompt" : ""}` : "Observed change in reward units"} />
        <Metric label="Accepted prompt changes" content={program ? String(program.accepted_count) : programs.length ? "—" : "0"} hint={program ? `${program.run_count} runs assigned to this workload` : "No workload selected"} />
        <Metric label="Current prompt" content={program ? `v${program.active_version}` : "Not tracked"} hint={program ? "Current supplementary instructions" : "Connect a prompt experiment to track revisions"} />
      </div>
      <RollingRewardChart data={history} program={matchingDetail} />
    </>}
    {program ? matchingDetail && <PromptEvolution program={matchingDetail} /> : <section id="prompt-optimization" aria-label="Prompt evolution" className="mt-6"><h2 className="m-0 text-sm font-semibold text-foreground">Prompt evolution</h2><p className="mt-2 text-sm text-muted-foreground">{programs.length ? "Choose a workload above to see its prompt versions and experiment decisions." : "No prompt optimization is connected to this agent yet."}</p><p className="mb-0 text-xs text-muted-foreground">A connected experiment records candidate instructions, baseline comparisons, accepted changes, and the prompt assigned to each run.</p></section>}
  </section>;
}

function Metric({ label, content, hint }: { label: string; content: string; hint: string }) {
  return <div><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="mb-1 mt-2 font-mono text-xl tabular-nums">{content}</p><p className="m-0 text-[11px] leading-relaxed text-muted-foreground">{hint}</p></div>;
}

export default function MonitoringPage() {
  useBreadcrumbs([{ label: "Monitoring" }], "rm-monitoring");
  const { data, error, reload } = useWorkbenchLoad(getMonitoring, 10000);
  return <RmPage title="Monitoring" description="Your agents, their prompts, and how their reward changes over time." wide>
    <ErrorNotice error={error} onRetry={() => void reload()} />
    {!data ? <p role="status" className="text-sm text-muted-foreground">Loading agents…</p> : <>
      {!data.agents.length ? <p className="text-sm text-muted-foreground">Connect an agent or import its traces to start monitoring.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-surface/50 text-xs text-muted-foreground"><tr className="border-y border-border"><th className="px-3 py-2.5">Agent</th><th className="px-3">Prompt optimization</th><th className="px-3">Current prompt</th><th className="px-3 text-right">Recorded runs</th><th className="px-3 text-right">Last activity</th></tr></thead><tbody>{data.agents.map((agent) => <AgentRow key={agent.agent} agent={agent} overview={data} />)}</tbody></table></div>}
      <GepaHistory runs={data.gepa} />
    </>}
  </RmPage>;
}

function AgentRow({ agent, overview }: { agent: MonitoredAgent; overview: MonitoringOverview }) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const programs = overview.programs.filter((p) => p.agent === agent.agent);
  const active = programs.filter((p) => p.status === "active");
  const status = active.length ? `${active.length} active workload${active.length === 1 ? "" : "s"}` : programs.length ? programs[0].status.replaceAll("_", " ") : "Not connected";
  const toggle = () => setExpanded((value) => !value);
  return <Fragment>
    <tr onClick={toggle} className={cn("h-8 cursor-pointer border-b border-border-subtle hover:bg-surface/60 focus-within:bg-surface/60 [&>td]:px-3 [&>td]:py-0", expanded && "bg-surface/60")}>
      <td><div className="flex items-center gap-2">
        <button type="button" aria-label={`${agent.display_name} details`} aria-expanded={expanded} aria-controls={detailsId} onClick={(event) => { event.stopPropagation(); toggle(); }} className="flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50"><ChevronRight className={cn("size-3.5 text-muted-foreground", expanded && "rotate-90")} /></button>
        <button type="button" aria-expanded={expanded} aria-controls={detailsId} className="cursor-pointer py-1 text-left font-medium hover:text-brand-600 hover:underline" onClick={(event) => { event.stopPropagation(); toggle(); }}>{agent.display_name}</button>
      </div></td>
      <td className="text-xs"><span className={cn("mr-2 inline-block h-1.5 w-1.5 rounded-full", active.length ? "bg-emerald-500" : "bg-muted-foreground/30")} />{status}</td>
      <td className="text-xs text-muted-foreground">{programs.length === 1 ? `v${programs[0].active_version}` : programs.length ? `${programs.length} workloads` : "—"}</td>
      <td className="text-right tabular-nums">{agent.trace_count}</td>
      <td className="text-right text-xs text-muted-foreground">{agent.last_seen ? relativeTime(agent.last_seen) : "Awaiting runs"}</td>
    </tr>
    {expanded && <tr id={detailsId}><td colSpan={5} className="border-b border-border p-0"><AgentDetail agent={agent} overview={overview} /></td></tr>}
  </Fragment>;
}
