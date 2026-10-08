"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { RmPage } from "@/components/reward-models/rm-ui";
import MonitoringNav from "@/components/reward-models/MonitoringNav";
import { ErrorNotice, useWorkbenchLoad } from "@/components/workbench/workbench-ui";
import { rmListAllTraces, rmListRewardModels, rmScoreTrace } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";
import { relativeTime } from "@/components/reward-models/rm-text";

export default function MonitoringPage() {
  useBreadcrumbs([{ label: "Monitoring" }], "rm-monitoring");
  const { data: models, error: modelsError, reload: reloadModels } = useWorkbenchLoad(rmListRewardModels);
  const [selectedModel, setSelectedModel] = useState("");
  const [agent, setAgent] = useState("all");
  const [scoring, setScoring] = useState(false);
  const [scoreStatus, setScoreStatus] = useState<string | null>(null);
  async function scoreRuns() {
    if (!modelId) return;
    setScoring(true); setScoreStatus(null);
    const modelName = available.find((model) => model.id === modelId)?.name ?? "Reward model";
    let queued = 0;
    try {
      for (const trace of visible.filter((t) => scoreOf(t) === null && t.can_score !== false)) { await rmScoreTrace(trace.id, modelId); queued++; }
      setScoreStatus(`${modelName}: ${queued} runs queued for scoring.`);
    } catch { setScoreStatus(`${modelName}: ${queued} runs queued. Couldn’t queue the remaining runs; try again.`); }
    finally { setScoring(false); }
  }
  const available = models?.filter((model) => model.status === "succeeded") ?? [];
  const modelId = selectedModel || available[0]?.id;
  const loader = useCallback(async () => ({ modelId, traces: modelId ? await rmListAllTraces("", modelId) : [] }), [modelId]);
  const { data, error, reload, loading } = useWorkbenchLoad(loader, 10000);
  const traces = data && data.modelId === modelId ? data.traces : [];
  const metrics = available.find((model) => model.id === modelId)?.metrics;
  const actionCredit = metrics?.action_scoring_version === 1 && metrics?.trace_scoring_version !== 1;
  const supportsScoring = metrics?.trace_scoring_version === 1 || actionCredit;
  const scoreOf = (trace: RmTraceSummary) => actionCredit ? trace.action_credit?.mean ?? null : trace.latest_score?.score ?? null;
  const agents = [...new Set(traces.map((trace) => trace.agent || trace.source_format))].sort();
  const visible = traces.filter((trace) => agent === "all" || (trace.agent || trace.source_format) === agent);
  const scored = visible.filter((trace) => scoreOf(trace) !== null);
  const values = scored.map((trace) => scoreOf(trace)!);
  const average = values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const chronological = [...scored].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  const low = values.length ? Math.min(...values) : 0, high = values.length ? Math.max(...values) : 1;
  const firstTime = chronological.length ? new Date(chronological[0].created_at).getTime() : 0;
  const lastTime = chronological.length ? new Date(chronological.at(-1)!.created_at).getTime() : 0;
  const x = (time: string) => 10 + (new Date(time).getTime() - firstTime) / (lastTime - firstTime || 1) * 580;
  return <RmPage title="Monitoring">
    <MonitoringNav />
    <ErrorNotice error={modelsError ?? error} onRetry={() => { void reloadModels(); void reload(); }} />
    {models && !available.length ? <p className="text-sm text-muted-foreground">Create a <Link className="underline" href="/reward-models/models">reward model</Link> from annotated traces to monitor your agent’s scores.</p> : <>
      <div className="mb-5 flex flex-wrap gap-3"><Select aria-label="Reward model" value={modelId ?? ""} onChange={setSelectedModel} disabled={scoring} options={available.map((model) => ({ value: model.id, label: model.name }))} className="h-9 min-w-52 px-3 text-sm" /><Select aria-label="Agent" value={agent} onChange={setAgent} options={[{ value: "all", label: "All agents" }, ...agents.map((name) => ({ value: name, label: name }))]} className="h-9 min-w-36 px-3 text-sm" /></div>
      <div className="mb-3 flex items-center justify-between gap-3"><p className="text-xs text-muted-foreground">{actionCredit ? "Mean action credit per recorded run from the selected reward model." : "Recorded runs scored by the selected reward model."}</p>{supportsScoring && <Button size="sm" variant="outline" disabled={scoring || !visible.some((t) => scoreOf(t) === null && t.can_score !== false)} onClick={() => void scoreRuns()}>{scoring ? "Queuing…" : "Score unscored runs"}</Button>}</div>
      {scoreStatus && <p role="status" className="text-xs text-muted-foreground">{scoreStatus}</p>}
      <div className="mb-6 grid grid-cols-3 gap-4">{[["Scored runs", `${scored.length} / ${visible.length}`], [actionCredit ? "Average action credit" : "Average score", average?.toFixed(2) ?? "—"], [actionCredit ? "Lowest action credit" : "Lowest score", values.length ? low.toFixed(2) : "—"]].map(([label, value]) => <div key={label} className="rounded-lg border border-border p-4"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 font-mono text-2xl tabular-nums">{value}</div></div>)}</div>
      {chronological.length > 1 && <figure className="mb-6 rounded-lg border border-border p-4"><figcaption className="mb-2 text-sm">{actionCredit ? "Action credit over time" : "Score over time"}</figcaption><svg viewBox="0 0 600 130" preserveAspectRatio="none" className="h-40 w-full" role="img" aria-label="Reward model scores ordered by recorded time"><polyline fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" className="text-brand-500" points={chronological.map((trace) => `${x(trace.created_at)},${110 - (scoreOf(trace)! - low) / (high - low || 1) * 90}`).join(" ")} />{chronological.map((trace) => <circle key={trace.id} cx={x(trace.created_at)} cy={110 - (scoreOf(trace)! - low) / (high - low || 1) * 90} r="3" fill="currentColor"><title>{trace.title}: {scoreOf(trace)!.toFixed(2)}</title></circle>)}</svg><div className="flex justify-between text-xs text-muted-foreground"><span>{new Date(chronological[0].created_at).toLocaleDateString()}</span><span>{new Date(chronological.at(-1)!.created_at).toLocaleDateString()}</span></div></figure>}
      {loading || data?.modelId !== modelId ? <p>Loading scores…</p> : !scored.length ? <p className="text-sm text-muted-foreground">No runs have a saved score from this model yet.</p> : <table className="w-full text-left text-sm"><thead><tr className="border-b border-border text-xs text-muted-foreground"><th className="py-2">Trace</th><th>Agent</th><th>Recorded</th><th className="text-right">{actionCredit ? "Action credit" : "Score"}</th></tr></thead><tbody>{scored.map((trace) => <tr key={trace.id} className="border-b border-border-subtle"><td className="py-3"><Link className="hover:underline" href={`/reward-models/traces/${trace.id}`}>{trace.title}</Link></td><td>{trace.agent || trace.source_format}</td><td>{relativeTime(trace.created_at)}</td><td className="text-right font-mono tabular-nums">{scoreOf(trace)!.toFixed(2)}</td></tr>)}</tbody></table>}
    </>}
  </RmPage>;
}
