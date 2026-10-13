"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
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
  return <section aria-label={`${agent.display_name} monitoring`} className="mt-6">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="m-0 text-base font-semibold text-foreground">{agent.display_name}</h2><p className="mb-0 mt-1 text-xs text-muted-foreground">{program ? `${program.name} · ${program.scope}` : "Performance across recorded runs"}</p></div><Button size="sm" variant="outline" disabled={!overview.models.length} onClick={() => setCreating(!creating)}>{creating ? "Cancel" : "Optimize prompt"}</Button></div>
    {creating && <div className="mb-5"><CreateOptimization initialModelId={modelId} initialAgent={agent.agent} /></div>}
    <div className="mb-4 flex flex-wrap items-center gap-3">
      {!!programs.length && <Select aria-label="Workload" value={selectedProgram} onChange={setProgram} options={[{ value: "recorded", label: "All recorded runs" }, ...programs.map((p) => ({ value: p.id, label: `${p.name} · ${p.scope}` }))]} className="h-9 max-w-lg px-3 text-xs" />}
      <Select aria-label="Reward model" value={modelId} onChange={setModel} disabled={!!program} options={[...overview.models.map((m) => ({ value: m.id, label: m.name })), ...(program && !overview.models.some((m) => m.id === program.reward_model_id) ? [{ value: program.reward_model_id, label: program.reward_model_name }] : [])]} className="h-9 min-w-48 px-3 text-xs" />
      <Select aria-label="Rolling window" value={String(window)} onChange={(s) => setWindow(Number(s))} options={[20, 50, 100].map((n) => ({ value: String(n), label: `Last ${n} scored runs` }))} className="h-9 px-3 text-xs" />
      {program && <RecordBadge value={program.status === "active" ? "optimizing" : program.status} />}
    </div>
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
  const [selected, setSelected] = useState("");
  const agent = data?.agents.find((a) => a.agent === selected) ?? data?.agents[0];
  return <RmPage title="Monitoring" description="Your agents, their prompts, and how their reward changes over time." wide>
    <ErrorNotice error={error} onRetry={() => void reload()} />
    {!data ? <p role="status" className="text-sm text-muted-foreground">Loading agents…</p> : <>
      {!data.agents.length ? <p className="text-sm text-muted-foreground">Connect an agent or import its traces to start monitoring.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-surface/50 text-xs text-muted-foreground"><tr className="border-y border-border"><th className="px-3 py-2.5">Agent</th><th className="px-3">Prompt optimization</th><th className="px-3">Current prompt</th><th className="px-3 text-right">Recorded runs</th><th className="px-3 text-right">Last activity</th></tr></thead><tbody>{data.agents.map((a) => {
        const programs = data.programs.filter((p) => p.agent === a.agent);
        const active = programs.filter((p) => p.status === "active");
        const status = active.length ? `${active.length} active workload${active.length === 1 ? "" : "s"}` : programs.length ? programs[0].status.replaceAll("_", " ") : "Not connected";
        return <tr key={a.agent} onClick={() => setSelected(a.agent)} className={cn("cursor-pointer border-b border-border-subtle", agent?.agent === a.agent ? "bg-brand-500/5" : "hover:bg-surface/60")}><td className="px-3 py-3"><button aria-pressed={agent?.agent === a.agent} className="w-full text-left font-medium" onClick={() => setSelected(a.agent)}>{a.display_name}</button></td><td className="px-3 text-xs"><span className={cn("mr-2 inline-block h-1.5 w-1.5 rounded-full", active.length ? "bg-emerald-500" : "bg-muted-foreground/30")} />{status}</td><td className="px-3 text-xs text-muted-foreground">{programs.length === 1 ? `v${programs[0].active_version}` : programs.length ? `${programs.length} workloads` : "—"}</td><td className="px-3 text-right tabular-nums">{a.trace_count}</td><td className="px-3 text-right text-xs text-muted-foreground">{a.last_seen ? relativeTime(a.last_seen) : "Awaiting runs"}</td></tr>;
      })}</tbody></table></div>}
      {agent && <AgentDetail key={agent.agent} agent={agent} overview={data} />}
      <GepaHistory runs={data.gepa} />
    </>}
  </RmPage>;
}
