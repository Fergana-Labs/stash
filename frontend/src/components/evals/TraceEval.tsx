"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ProbabilityBars, RubricAnswersView } from "@/components/intuitions/ProbabilityBars";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGet, imList, imPredict, type ModelDetail, type ModelSummary, type Prediction } from "@/lib/intuition-api";
import type { RmTraceDetail } from "@/lib/types";

export default function TraceEval({ trace }: { trace: RmTraceDetail }) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [result, setResult] = useState<Prediction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <>
    <Button size="xs" variant="outline" onClick={async () => {
      setOpen(true); setError(""); setBusy(true);
      try { const next = (await imList()).models.filter((m) => m.active_version_id); setModels(next); setSelected(next[0]?.id ?? ""); setResult(null); }
      catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
    }}>Run eval</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto"><DialogHeader><DialogTitle>Evaluate this trace</DialogTitle><DialogDescription>{trace.title}</DialogDescription></DialogHeader>
      <div className="flex items-center gap-3"><Select aria-label="Eval" value={selected} onChange={(next) => { setSelected(next); setResult(null); }} disabled={busy || !models.length} options={models.map((m) => ({ value: m.id, label: m.name }))} /><Button size="sm" disabled={busy || !selected} onClick={async () => {
        setBusy(true); setError(""); setResult(null);
        try {
          const next = await imGet(selected); setDetail(next);
          const item = { title: trace.title, trace_id: trace.id, steps: trace.steps.map(({ index, role, content, tool_name, tool_input }) => ({ index, role, content, tool_name, tool_input })) };
          setResult(await imPredict(selected, item));
        } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
      }}>{busy ? "Evaluating…" : "Run"}</Button></div>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      {!busy && !models.length && <p className="text-xs text-muted-foreground">Create and activate an <Link href="/reward-models/evals" className="underline">eval</Link> first.</p>}
      {result && <section aria-label="Trace eval scorecard" className="space-y-4"><div className="flex items-baseline gap-3"><strong className="text-xl">{result.label}</strong><span className="text-xs text-muted-foreground">{Math.round(result.confidence * 100)}% confidence · v{result.version}</span></div><ProbabilityBars probabilities={result.probabilities} order={Object.keys(result.probabilities)} highlight={result.label} /><RubricAnswersView rubric={detail?.active?.rubric ?? []} answers={result.rubric} /><Link href={`/reward-models/evals/${selected}`} className="text-xs underline">Review this call or correct the eval</Link><p className="text-xs text-muted-foreground">This evaluates the trace as a whole. It does not assign causal credit to individual actions.</p></section>}
    </DialogContent></Dialog>
  </>;
}
