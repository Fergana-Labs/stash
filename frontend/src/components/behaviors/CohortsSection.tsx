"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Pickaxe } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { errorMessage } from "@/components/reward-models/rm-text";
import { FieldLabel } from "@/components/behaviors/behavior-ui";
import { COHORT_DIMENSIONS, getCohorts, humanize, type Cohort, type CohortBy, type CohortOverview } from "@/lib/behaviors-api";
import { imEditDraft, imGet, imList, imMineProduction, type MinedCriteria, type ModelSummary, type RubricQuestion } from "@/lib/intuition-api";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Traces grouped by one dimension, with each group's stats and "Add to eval → mine criteria". */
export default function CohortsSection({ by, days }: { by: CohortBy; days: number }) {
  const [data, setData] = useState<CohortOverview | null>(null);
  const [error, setError] = useState("");
  const [mining, setMining] = useState<Cohort | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    getCohorts(by, days).then((d) => { if (!cancelled) { setData(d); setError(""); } }).catch((e) => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [by, days]);

  // Outcome, satisfaction and tool-use keys are enums; agent, behavior and task names are shown as recorded.
  const label = (key: string) => by === "outcome" || by === "satisfaction" || by === "tool_use" ? humanize(key) : key;
  return <section aria-label="Cohorts">
    {error && <p role="alert" className="mb-2 text-xs text-destructive">{error}</p>}
    <div className="overflow-x-auto rounded border border-border"><table aria-label="Cohorts" className="w-full min-w-[960px] table-fixed text-left text-xs">
      <thead className="border-b border-border bg-surface/60 text-muted-foreground"><tr className="h-8 [&>th]:px-3 [&>th]:font-medium">
        <th className="w-40">{COHORT_DIMENSIONS.find((d) => d.value === by)?.label ?? "Group"}</th><th className="w-36">Traces</th><th className="w-20 text-right">Frustrated</th><th className="w-20 text-right">Corrected</th><th className="w-20 text-right">Tool calls</th><th>Top behaviors</th><th className="w-52">Sample</th><th className="w-32" />
      </tr></thead>
      <tbody>
        {data?.cohorts.map((c) => <tr key={c.key} className="border-b border-border align-top hover:bg-surface/60 [&>td]:px-3 [&>td]:py-2">
          <td className="truncate font-medium" title={c.key}>{label(c.key)}</td>
          <td><div className="flex items-center gap-2"><span className="w-8 text-right tabular-nums">{c.traces}</span><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-brand-500/70" style={{ width: pct(c.share) }} /></div><span className="w-8 text-right tabular-nums text-muted-foreground">{pct(c.share)}</span></div></td>
          <td className="text-right tabular-nums">{pct(c.frustrated_rate)}</td>
          <td className="text-right tabular-nums">{pct(c.correction_rate)}</td>
          <td className="text-right tabular-nums">{c.avg_tool_calls.toFixed(1)}</td>
          <td><div className="flex flex-wrap gap-1">{c.top_behaviors.map(([name, n]) => <span key={name} className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px]">{name}<span className="tabular-nums text-muted-foreground">{n}</span></span>)}{!c.top_behaviors.length && <span className="text-muted-foreground">—</span>}</div></td>
          <td><ul className="m-0 list-none space-y-0.5 p-0">{c.sample.slice(0, 3).map((s) => <li key={s.trace_id} className="truncate"><Link href={`/reward-models/traces/${s.trace_id}`} className="hover:underline">{s.title || "Untitled trace"}</Link></li>)}</ul></td>
          <td className="text-right"><Button size="xs" variant="outline" title="Mine criteria from this group's user reactions and add them to an eval" onClick={() => setMining(c)}><Pickaxe />Add to eval</Button></td>
        </tr>)}
        {!data && !error && <tr><td colSpan={8} className="px-3 py-6"><span role="status" className="text-muted-foreground">Loading groups…</span></td></tr>}
        {data && !data.cohorts.length && <tr><td colSpan={8} className="px-3 py-8 text-muted-foreground">No traces in this time range.</td></tr>}
      </tbody>
    </table></div>
    <MineCriteriaDialog cohort={mining} by={by} days={days} label={mining ? label(mining.key) : ""} onClose={() => setMining(null)} />
  </section>;
}

/** Pick an eval, mine candidate criteria from the cohort's production reactions, and add the ones you want to its draft. */
function MineCriteriaDialog({ cohort, by, days, label, onClose }: { cohort: Cohort | null; by: CohortBy; days: number; label: string; onClose: () => void }) {
  const [evals, setEvals] = useState<ModelSummary[] | null>(null);
  const [evalId, setEvalId] = useState("");
  const [mined, setMined] = useState<MinedCriteria | null>(null);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const open = cohort !== null;

  useEffect(() => {
    if (!open) { setMined(null); setAdded(new Set()); setError(""); return; }
    if (evals) return;
    imList().then((r) => { setEvals(r.models); setEvalId((cur) => cur || r.models[0]?.id || ""); }).catch((e) => setError(errorMessage(e)));
  }, [open, evals]);

  async function mine() {
    if (!cohort) return;
    setBusy(true); setError(""); setMined(null); setAdded(new Set());
    try { setMined(await imMineProduction(evalId, { by, key: cohort.key, days })); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  async function addToDraft(q: RubricQuestion) {
    setBusy(true); setError("");
    try {
      const detail = await imGet(evalId);
      const rubric = (detail.draft ?? detail.active)?.rubric ?? [];
      if (!rubric.some((r) => r.id === q.id)) await imEditDraft(evalId, { rubric: [...rubric, q] });
      setAdded((cur) => new Set(cur).add(q.id));
      toast.success("Added to the eval’s draft criteria");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  return <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}><DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
    <DialogHeader><DialogTitle>Add to eval: mine criteria</DialogTitle><DialogDescription>{cohort ? `From users’ corrections, repeats and pushback in “${label}” (${cohort.traces} traces).` : ""}</DialogDescription></DialogHeader>
    <div className="grid gap-3">
      <div className="flex items-end gap-2">
        <div className="flex-1"><FieldLabel label="Eval">{evals && evals.length
          ? <Select aria-label="Eval" value={evalId} onChange={(v) => { setEvalId(v); setMined(null); }} options={evals.map((m) => ({ value: m.id, label: m.name }))} />
          : <p className="text-xs text-muted-foreground">{evals ? "No evals yet. Create one under Evals first." : "Loading evals…"}</p>}</FieldLabel></div>
        <Button size="sm" disabled={!evalId || busy} onClick={() => void mine()}>{busy && !mined ? "Mining…" : "Mine"}</Button>
      </div>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      {mined && <div className="grid gap-3 text-xs">
        <p className="m-0">{mined.rationale}</p>
        <p className="m-0 text-[11px] text-muted-foreground">{mined.votes} user reactions across {mined.cohort.traces} traces.</p>
        {mined.examples.length > 0 && <ul aria-label="Example reactions" className="m-0 grid list-none gap-1.5 p-0">{mined.examples.map((ex, i) => <li key={i} className="rounded border border-border px-2.5 py-1.5">
          <span className="mr-1.5 rounded bg-muted px-1 text-[10px] text-muted-foreground">{humanize(ex.reaction)}</span>
          <span className="text-muted-foreground">Agent:</span> <span className="line-clamp-2 inline">{ex.agent_said}</span>
          <p className="m-0 mt-0.5"><span className="text-muted-foreground">User:</span> {ex.user_replied}</p>
        </li>)}</ul>}
        <div className="grid gap-1.5">
          <h3 className="m-0 text-[12px] font-semibold">Proposed questions</h3>
          {mined.questions.map((q) => <div key={q.id} className="flex items-start gap-2 rounded border border-border px-2.5 py-1.5">
            <div className="min-w-0 flex-1"><span className="mr-1.5 text-[10.5px] text-muted-foreground">{humanize(q.type)}</span>{q.prompt}</div>
            <Button size="xs" variant="outline" disabled={busy || added.has(q.id)} onClick={() => void addToDraft(q)}>{added.has(q.id) ? "Added" : "Add to eval"}</Button>
          </div>)}
          {!mined.questions.length && <p className="m-0 text-muted-foreground">No new questions proposed.</p>}
        </div>
        {added.size > 0 && <Link href={`/reward-models/evals/${evalId}`} className="text-[11.5px] underline">Open the eval to review the draft</Link>}
      </div>}
    </div>
    <DialogFooter><Button size="sm" variant="outline" onClick={onClose}>Close</Button></DialogFooter>
  </DialogContent></Dialog>;
}
