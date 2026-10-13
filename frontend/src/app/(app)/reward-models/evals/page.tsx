"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { ChevronRight, Plus, Search } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imList, type ModelSummary } from "@/lib/intuition-api";
import EvalWorkspace from "@/components/evals/EvalWorkspace";
import AgentUsagePanel from "@/components/intuitions/AgentUsagePanel";
import { cn } from "@/lib/utils";

export default function EvalsPage() {
  useBreadcrumbs([{ label: "Evals" }], "evals");
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [connectedId, setConnectedId] = useState("");
  const load = useCallback(async () => { try { setModels((await imList()).models); setError(""); } catch (e) { setError(errorMessage(e)); } }, []);
  useEffect(() => { void load(); }, [load]);
  const visible = models?.filter((model) => `${model.name} ${model.active_description ?? model.draft_description ?? ""}`.toLowerCase().includes(query.toLowerCase())) ?? [];
  const connected = models?.find((model) => model.id === connectedId) ?? models?.[0];
  return <RmPage title="Evals" description="Teach an eval what good looks like with examples and feedback." wide actions={<Button size="sm" asChild><Link href="/reward-models/evals/new"><Plus />New eval</Link></Button>}>
    {error && <p role="alert" className="text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    <label className="mb-3 flex h-8 w-64 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Search evals" placeholder="Search evals…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label>
    <table aria-label="Evals" className="w-full text-left text-xs"><thead className="border-y border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Eval</th><th>Status</th><th className="text-right">Examples</th><th className="text-right">Holdout agreement</th></tr></thead><tbody>
      {visible.map((model) => <Fragment key={model.id}><tr className={cn("h-8 cursor-pointer border-b border-border hover:bg-surface/60 [&>td]:px-3", expanded === model.id && "bg-surface/60")} onClick={() => setExpanded(expanded === model.id ? null : model.id)}>
        <td><button aria-expanded={expanded === model.id} aria-controls={`eval-${model.id}`} className="flex items-center gap-2 py-1 text-left font-medium"><ChevronRight className={cn("size-3.5 text-muted-foreground", expanded === model.id && "rotate-90")} />{model.name}</button></td><td>{model.active_number === null ? "Draft" : `Ready · v${model.active_number}`}</td><td className="text-right tabular-nums">{model.examples}</td><td className="text-right tabular-nums">{model.active_metrics?.eval.accuracy == null ? "—" : `${Math.round(model.active_metrics.eval.accuracy * 100)}% · ${model.active_metrics.eval.n} checked`}</td>
      </tr>{expanded === model.id && <tr id={`eval-${model.id}`}><td colSpan={4} className="border-b border-border p-0"><EvalWorkspace id={model.id} embedded onUpdated={() => void load()} /></td></tr>}</Fragment>)}
      {!models && !error && <tr><td colSpan={4} className="py-6"><span role="status" className="text-muted-foreground">Loading evals…</span></td></tr>}
      {models && !visible.length && <tr><td colSpan={4} className="py-8 text-muted-foreground">{models.length ? "No matching evals." : "Create your first eval from good and bad outputs, notes, or annotated traces."}</td></tr>}
    </tbody></table>
    {connected && <div className="mt-5"><AgentUsagePanel modelId={connected.id} outputType={connected.output_type} sample="An output or proposed agent action" models={models?.map((model) => ({ value: model.id, label: model.name }))} onModelChange={setConnectedId} /></div>}
  </RmPage>;
}
