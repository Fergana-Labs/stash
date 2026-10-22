"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { Button } from "@/components/ui/button";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import { evalList, type Eval } from "@/lib/evals-api";
import { EvalsViewToggle } from "@/components/test-sets/test-set-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imList, type ModelSummary } from "@/lib/intuition-api";

const actionClass = "h-[26px] gap-1.5 rounded-[4px] px-2 text-[11px] font-normal shadow-none [&_svg]:size-3";

export default function EvalsPage() {
  useBreadcrumbs([{ label: "Evals" }], "evals");
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [judged, setJudged] = useState<Eval[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const router = useRouter();
  const load = useCallback(async () => {
    try {
      const [evals, made] = await Promise.all([imList(), evalList().catch(() => [] as Eval[])]);
      setJudged(made);
      setModels(evals.models); setError("");
    } catch (e) { setError(errorMessage(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const rows = [
    ...(models ?? []).map((model) => {
      // Evals made from examples are ready once built and count their own examples.
      const made = judged.find((e) => e.id === model.id);
      if (made) return { id: model.id, name: made.name, draft: !made.ready, href: `/reward-models/evals/${model.id}`,
        description: made.build?.summary ?? made.instructions, examples: made.examples.good + made.examples.bad, metrics: model.active_metrics };
      return { id: model.id, name: model.name, draft: model.active_number == null,
        href: `/reward-models/evals/${model.id}`,
        description: model.active_description ?? model.draft_description ?? "", examples: model.examples, metrics: model.active_metrics };
    }),
  ];
  const visible = rows.filter((row) => `${row.name} ${row.description}`.toLowerCase().includes(query.toLowerCase()));
  return <EvalPageFrame title="Evals" description="Create, test, and review evaluators." actions={<Button size="xs" className={actionClass} asChild><Link href="/reward-models/evals/new"><Plus />New eval</Link></Button>}>
    <EvalsViewToggle view="evals" />
    {error && <p role="alert" className="text-xs text-destructive">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    <div className="mb-3 flex items-center justify-between gap-3"><label className="flex h-8 w-64 items-center gap-2 rounded-md border border-border px-2"><Search className="size-3 text-muted-foreground" /><input aria-label="Search evals" placeholder="Search evals…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><span className="text-xs text-muted-foreground">{models ? `${visible.length} evals` : ""}</span></div>
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Evals" className="w-full min-w-[640px] text-left text-xs"><thead className="border-y border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium"><th>Eval</th><th className="text-right">Examples</th><th className="text-right">Holdout agreement</th></tr></thead><tbody>
      {visible.map((model) => <tr key={model.id} className="h-11 cursor-pointer border-b border-border hover:bg-surface/60 [&>td]:px-3" onClick={(event) => {
        if ((event.target as HTMLElement).closest("a")) return;
        router.push(model.href);
      }}>
        <td><div className="flex items-center gap-2"><Link href={model.href} className="block py-2 text-left font-medium">{model.name}</Link>{model.draft && <span className="ml-auto shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">Draft</span>}</div></td><td className="text-right tabular-nums">{model.examples}</td><td className="text-right tabular-nums">{model.metrics?.eval.accuracy == null ? "—" : `${Math.round(model.metrics.eval.accuracy * 100)}%, ${model.metrics.eval.n} checked`}</td>
      </tr>)}
      {!models && !error && <tr><td colSpan={3} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading evals…</span></td></tr>}
      {models && !visible.length && <tr><td colSpan={3} className="px-3 py-8 text-muted-foreground">{rows.length ? "No matching evals." : "Create your first eval from good and bad outputs, notes, or annotated traces."}</td></tr>}
    </tbody></table></div>
  </EvalPageFrame>;
}
