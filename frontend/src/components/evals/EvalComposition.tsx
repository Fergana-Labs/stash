"use client";

import { useCallback, useEffect, useState } from "react";
import { Minus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imCredit, imEditDraft, imList, type Credit, type ModelDetail, type ModelSummary, type RubricQuestion } from "@/lib/intuition-api";
import { evalSurfaceClass } from "./eval-ui";

const percent = (n: number | null | undefined) => n == null ? "—" : `${Math.round(n * 100)}%`;

/** Other evals whose decisions this eval uses as signals. Applied on the next Save. */
export function EvalSignals({ id, detail, busy, onChanged }: { id: string; detail: ModelDetail; busy: boolean; onChanged: () => void }) {
  const [evals, setEvals] = useState<ModelSummary[]>([]);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  useEffect(() => { void imList().then((r) => setEvals(r.models)).catch((e) => setError(errorMessage(e))); }, []);
  const rubric = (detail.draft ?? detail.active)?.rubric ?? [];
  const signals = rubric.filter((q) => q.type === "eval");
  const saved = new Set((detail.active?.rubric ?? []).filter((q) => q.type === "eval").map((q) => q.eval_id));
  const available = evals.filter((e) => e.id !== id && e.active_version_id && !signals.some((q) => q.eval_id === e.id));
  async function update(next: RubricQuestion[]) {
    setWorking(true); setError("");
    try { await imEditDraft(id, { rubric: next }); onChanged(); } catch (e) { setError(errorMessage(e)); } finally { setWorking(false); }
  }
  return <section aria-label="Signals from other evals" className="space-y-2 rounded border border-border p-4">
    <h2 className="text-sm font-semibold">Signals from other evals</h2>
    <p className="text-xs text-muted-foreground">Use another eval’s decision as a criterion. This eval learns how much it matters; the other eval’s saved version is pinned.</p>
    {!!signals.length && <ul className="space-y-1 text-xs">{signals.map((q) => <li key={q.id} className="flex items-center gap-2">
      <span className="min-w-0 flex-1 truncate">{q.prompt}</span>
      {!saved.has(q.eval_id) && <span className="text-[10px] text-muted-foreground">applies on Save</span>}
      <Button size="icon-sm" variant="ghost" aria-label={`Stop using ${q.prompt}`} disabled={busy || working} onClick={() => void update(rubric.filter((r) => r.id !== q.id))}><Minus /></Button>
    </li>)}</ul>}
    {available.length ? <div className="flex gap-2">
      <Select contentClassName={`${evalSurfaceClass} rounded-[4px] shadow-sm`} aria-label="Eval to use as a signal" value={choice} onChange={setChoice} options={[{ value: "", label: "Choose an eval" }, ...available.map((e) => ({ value: e.id, label: e.name }))]} className="h-7 min-w-0 flex-1 px-2 text-xs" />
      <Button size="xs" variant="outline" disabled={busy || working || !choice} onClick={() => { const evalId = choice; setChoice(""); void update([...rubric, { id: "", type: "eval", prompt: "", criteria: {}, eval_id: evalId }]); }}>Use</Button>
    </div> : <p className="text-[11px] text-muted-foreground">{signals.length ? "No other saved evals to add." : "Save another eval to use its decision here."}</p>}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
  </section>;
}

/** Whether this eval's decisions inside runs predict how those runs ended. */
export function OutcomeLink({ id }: { id: string }) {
  const [credit, setCredit] = useState<Credit | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => setCredit(await imCredit(id)), [id]);
  useEffect(() => { void load().catch((e) => setError(errorMessage(e))); }, [load]);
  if (error) return <p role="alert" className="text-xs text-destructive">{error}</p>;
  if (!credit) return null;
  const span = Math.max(0.5, ...(credit.weights ?? []).flatMap((w) => [Math.abs(w.low ?? w.weight), Math.abs(w.high ?? w.weight)]));
  const at = (n: number) => `${50 + n / span * 50}%`;
  return <section aria-label="Outcome link" className="space-y-3 rounded border border-border p-4">
    <div><h3 className="text-sm font-medium">Do its decisions predict outcomes?</h3>
      <p className="text-xs text-muted-foreground">Calls tagged with a run, and the outcome reported for that run later (0 failed … 1 succeeded). {credit.runs} runs with outcomes · {percent(credit.success_rate)} succeeded.</p></div>
    <table className="w-full text-left text-xs"><thead><tr className="border-b border-border text-muted-foreground"><th className="py-1.5 font-medium">When it decided</th><th className="pl-4 text-right font-medium">Runs</th><th className="pl-4 text-right font-medium">Succeeded</th></tr></thead>
      <tbody>{credit.by_decision.map((d) => <tr key={d.decision} className="border-b border-border/60"><td className="py-1.5">{d.decision}</td><td className="pl-4 text-right tabular-nums">{d.runs}</td><td className="pl-4 text-right tabular-nums">{percent(d.success_rate)}</td></tr>)}</tbody></table>
    {!credit.ready ? <p className="text-xs text-muted-foreground">{credit.reason}</p> : <>
      <div className="space-y-1.5"><div className="text-[11px] font-medium text-muted-foreground">Learned link to success (weight with 95% interval)</div>
        {credit.weights!.map((w) => <div key={w.decision} className="grid grid-cols-[minmax(0,90px)_minmax(0,1fr)_52px] items-center gap-2 text-[11px]" title={`Interval ${w.low?.toFixed(2) ?? "—"} to ${w.high?.toFixed(2) ?? "—"}`}>
          <span className="truncate">{w.decision}</span>
          <span className="relative h-2 rounded-full bg-border/60"><span className="absolute top-0 h-2 w-px bg-foreground/40" style={{ left: "50%" }} />
            {w.low != null && w.high != null && <span className="absolute top-[3px] h-0.5 bg-foreground/30" style={{ left: at(w.low), width: `calc(${at(w.high)} - ${at(w.low)})` }} />}
            <span className="absolute top-0 size-2 -translate-x-1/2 rounded-full bg-primary" style={{ left: at(w.weight) }} /></span>
          <span className="text-right tabular-nums">{w.weight > 0 ? "+" : ""}{w.weight.toFixed(2)}</span>
        </div>)}
      </div>
      <p className="text-xs">Predicts run outcomes {percent(credit.cv_accuracy)} of the time (cross-validated). {(credit.calls_by_credit ?? []).filter((c) => c.suspect).length} calls pushed against their run’s outcome and are queued in Worth labeling.</p>
    </>}
  </section>;
}
