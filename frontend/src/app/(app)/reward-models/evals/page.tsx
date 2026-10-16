"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { EvalsViewToggle } from "@/components/test-sets/test-set-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wizardSessionName, wzSessions, type WizardSession } from "@/lib/wizard-api";
import { tasteGet, type TasteWorkspace } from "@/lib/taste-api";
import { imList, type ModelSummary } from "@/lib/intuition-api";

const actionClass = "h-[26px] gap-1.5 rounded-[4px] px-2 text-[11px] font-normal shadow-none [&_svg]:size-3";

export default function EvalsPage() {
  useBreadcrumbs([{ label: "Evals" }], "evals");
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [sessions, setSessions] = useState<WizardSession[]>([]);
  const [taste, setTaste] = useState<TasteWorkspace | null>(null);
  const [showDrafts, setShowDrafts] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const router = useRouter();
  const load = useCallback(async () => {
    try {
      const [evals, drafts, tasteWorkspace] = await Promise.all([imList(), wzSessions(), tasteGet().catch(() => null)]);
      setTaste(tasteWorkspace);
      setModels(evals.models); setSessions(drafts.sessions); setError("");
    } catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const rows = [
    ...(models ?? []).map((model) => {
      const session = sessions.find((s) => s.model_id === model.id);
      return { id: model.id, name: model.name, draft: model.id===taste?.model_id ? !taste.published : model.active_number == null,
        href: model.id===taste?.model_id && taste.published ? `/reward-models/evals/${model.id}` : model.active_number == null && session ? `/reward-models/wizard/${session.id}` : `/reward-models/evals/${model.id}`,
        description: model.active_description ?? model.draft_description ?? "", examples: model.id===taste?.model_id ? taste.examples.length : model.examples, metrics: model.active_metrics };
    }),
    ...sessions.filter((s) => !s.model_id).map((session) => ({
      id: `wizard:${session.id}`, name: wizardSessionName(session), draft: true,
      href: `/reward-models/wizard/${session.id}`, description: session.draft_input ?? "", examples: 0, metrics: null,
    })),
  ];
  const archived = new Set(taste?.related_eval_ids ?? []);
  // The website demo in progress always shows, even before it has examples.
  const visible = rows.filter(row => !taste || showDrafts || row.id === taste.model_id || (!archived.has(row.id) && !(row.draft && row.examples === 0))).filter((row) => `${row.name} ${row.description}`.toLowerCase().includes(query.toLowerCase()));
  return <EvalPageFrame title="Evals" description="Create, test, and review evaluators." actions={<Button size="xs" className={actionClass} asChild><Link href="/reward-models/evals/new"><Plus />New eval</Link></Button>}>
    <EvalsViewToggle view="evals" />
    <label className="mb-3 flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={showDrafts} onChange={event=>setShowDrafts(event.target.checked)}/>Show empty drafts and supporting taste evals</label>
    {error && <p role="alert" className="text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    <div className="mb-3 flex items-center justify-between gap-3"><label className="flex h-8 w-64 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Search evals" placeholder="Search evals…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><span className="text-xs text-muted-foreground">{models ? `${visible.length} evals` : ""}</span></div>
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Evals" className="w-full min-w-[640px] text-left text-xs"><thead className="border-y border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Eval</th><th className="text-right">Examples</th><th className="text-right">Holdout agreement</th></tr></thead><tbody>
      {visible.map((model) => <tr key={model.id} className="h-11 cursor-pointer border-b border-border hover:bg-surface/60 [&>td]:px-3" onClick={(event) => {
        if ((event.target as HTMLElement).closest("a")) return;
        router.push(model.href);
      }}>
        <td><div className="flex items-center gap-2"><Link href={model.href} className="block py-2 text-left font-medium">{model.name}</Link>{model.draft && <span className="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">Draft</span>}</div></td><td className="text-right tabular-nums">{model.examples}</td><td className="text-right tabular-nums">{model.metrics?.eval.accuracy == null ? "—" : `${Math.round(model.metrics.eval.accuracy * 100)}% · ${model.metrics.eval.n} checked`}</td>
      </tr>)}
      {!models && !error && <tr><td colSpan={3} className="py-6"><span role="status" className="text-muted-foreground">Loading evals…</span></td></tr>}
      {models && !visible.length && <tr><td colSpan={3} className="py-8 text-muted-foreground">{rows.length ? "No matching evals." : "Create your first eval from good and bad outputs, notes, or annotated traces."}</td></tr>}
    </tbody></table></div>
  </EvalPageFrame>;
}
