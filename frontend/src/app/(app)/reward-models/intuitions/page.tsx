"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Plus, Search } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import CreateModelDialog from "@/components/intuitions/CreateModelDialog";
import LoadExampleButton from "@/components/intuitions/LoadExampleButton";
import { pct } from "@/components/intuitions/im-helpers";
import { LoadError } from "@/components/intuitions/im-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imList, type JudgeStatus, type ModelSummary } from "@/lib/intuition-api";

export default function IntuitionsPage() {
  useBreadcrumbs([{ label: "Intuition models" }], "im-list");
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [judge, setJudge] = useState<JudgeStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const load = useCallback(async () => {
    setLoadError(null);
    try { const result = await imList(); setModels(result.models); setJudge(result.judge); }
    catch (e) { setLoadError(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const visible = (models ?? []).filter((m) => `${m.name} ${m.active_description ?? ""} ${m.draft_description ?? ""}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="scroll-thin h-full overflow-y-auto px-6 pt-5 pb-12">
    <header className="mb-4 flex items-center justify-between gap-3">
      <h1 className="m-0 font-display text-[18px] font-semibold tracking-tight">Intuition models</h1>
      <div className="flex items-center gap-2"><LoadExampleButton /><Button size="sm" onClick={() => setCreating(true)}><Plus />New model</Button></div>
    </header>
    <CreateModelDialog open={creating} onOpenChange={setCreating} />
    {judge && !judge.configured && <p className="mb-4 text-xs text-muted-foreground">Live predictions are unavailable until the judge is connected. You can explore the bundled example with its recorded results.</p>}
    {loadError ? <LoadError what="intuition models" message={loadError} onRetry={() => void load()} /> : <>
      <div className="mb-3 flex items-center justify-between gap-3">
        <label className="flex h-7 w-56 items-center gap-1.5 rounded-md border border-border px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20"><Search className="size-3.5 text-muted-foreground" /><input aria-label="Search intuition models" placeholder="Search models…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label>
        {models && <span className="text-xs text-muted-foreground">{visible.length} model{visible.length === 1 ? "" : "s"}</span>}
      </div>
      <div className="overflow-x-auto border-y border-border"><table aria-label="Intuition models" className="w-full min-w-[780px] table-fixed text-left text-[12.5px]">
        <thead className="border-b border-border bg-surface/60 text-[11.5px] text-muted-foreground"><tr className="h-7 [&>th]:px-3 [&>th]:font-medium"><th>Model</th><th className="w-28">Type</th><th className="w-32">Version</th><th className="w-24 text-right">Examples</th><th className="w-28 text-right">To review</th><th className="w-32 text-right">Eval accuracy</th><th className="w-44 text-right">Updated</th></tr></thead>
        <tbody>{visible.map((model) => <tr key={model.id} className="h-8 border-b border-border-subtle last:border-0 hover:bg-surface/60 [&>td]:px-3"><td><Link href={`/reward-models/intuitions/${model.id}`} className="block truncate font-medium hover:text-brand-600 hover:underline">{model.name}</Link></td><td className="text-muted-foreground">{model.output_type === "choice" ? "Classifier" : "Preference"}</td><td>{model.active_number != null ? `v${model.active_number} active` : "Draft"}</td><td className="text-right tabular-nums">{model.examples}</td><td className="text-right tabular-nums">{model.inbox || "—"}</td><td className="text-right tabular-nums">{pct(model.active_metrics?.eval?.accuracy)}</td><td className="text-right text-[11.5px] text-muted-foreground"><time dateTime={model.updated_at}>{new Date(model.updated_at).toLocaleString()}</time></td></tr>)}</tbody>
      </table>{!models ? <p role="status" className="py-8 text-center text-sm text-muted-foreground">Loading models…</p> : !visible.length && <div className="py-10 text-center"><p className="text-sm font-medium">{query ? "No matching models" : "No intuition models yet"}</p><p className="mt-1 text-xs text-muted-foreground">{query ? "Try a different search." : "Create a model or load the support-reply example to try the playground."}</p></div>}</div>
    </>}
  </div>;
}
