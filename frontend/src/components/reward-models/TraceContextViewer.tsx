"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { rmGetTrace } from "@/lib/api";
import type { RmTraceDetail } from "@/lib/types";
import { errorMessage } from "./rm-text";
import { traceCheckpoint } from "./trace-checkpoint";

export default function TraceContextViewer({ traceId }: { traceId: string }) {
  const params = useSearchParams();
  const requested = params.get("step");
  const [trace, setTrace] = useState<RmTraceDetail | null>(null);
  const [stepId, setStepId] = useState(requested ?? "");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setTrace(await rmGetTrace(traceId)); setError(null); }
    catch (e) { setError(errorMessage(e)); }
  }, [traceId]);
  useEffect(() => { void load(); }, [load]);
  useBreadcrumbs([{ label: "Traces", href: "/reward-models" }, { label: trace?.title ?? "Trace", href: `/reward-models/traces/${traceId}` }, { label: "Context" }], "trace-context");
  const selected = trace?.steps.find((step) => step.id === stepId) ?? (!stepId ? trace?.steps.find((step) => step.role === "assistant") ?? trace?.steps[0] : undefined);
  const checkpoint = trace && selected ? traceCheckpoint(trace, selected.id) : null;
  function download() {
    if (!checkpoint) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(checkpoint, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `trace-${traceId}-before-step-${selected!.index + 1}.json`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="scroll-thin h-full overflow-y-auto p-6">
    <header className="mb-5 flex items-center gap-3"><Link href={`/reward-models/traces/${traceId}${selected ? `#step-${selected.id}` : ""}`} aria-label="Back to trace"><ArrowLeft className="size-4" /></Link><h1 className="font-display text-lg font-semibold">Context at a checkpoint</h1><Button className="ml-auto" size="sm" variant="outline" disabled={!checkpoint} onClick={download}><Download />Download checkpoint</Button></header>
    <p className="mb-5 text-sm text-muted-foreground">Inspect recorded messages before a step. This reconstructs trace history; it does not establish the exact context window after compaction, truncation, or unrecorded instructions.</p>
    {error ? <div role="alert">{error}<Button variant="outline" onClick={() => void load()}>Retry</Button></div> : !trace ? <p role="status">Loading trace…</p> : <>
      <label className="mb-5 block text-sm font-medium">Checkpoint<select aria-label="Checkpoint" className="mt-2 block w-full rounded-md border border-border bg-background p-2" value={selected?.id ?? stepId} onChange={(e) => setStepId(e.target.value)}>{stepId && !selected && <option value={stepId}>Recorded step no longer exists</option>}{trace.steps.map((step) => <option key={step.id} value={step.id}>Before step {step.index + 1}, {step.role}{step.tool_name ? ` → ${step.tool_name}` : ""}</option>)}</select></label>
      {!selected ? <p role="alert">{trace.steps.length ? "This checkpoint is no longer available. Select another step." : "This trace has no recorded steps."}</p> : <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
        <section className="min-w-0 rounded-lg border border-border"><h2 className="border-b border-border p-4 text-sm font-medium">Recorded context, {checkpoint!.messages.length} messages</h2><div className="divide-y divide-border">{checkpoint!.messages.map((step) => <article key={step.id} className="p-4"><h3 className="mb-2 text-xs font-medium">{step.index + 1}, {step.role}{step.tool_name ? ` → ${step.tool_name}` : ""}</h3><pre className="whitespace-pre-wrap break-words font-sans text-sm">{step.content}</pre>{step.tool_input && <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs text-muted-foreground">{JSON.stringify(step.tool_input, null, 2)}</pre>}</article>)}{!checkpoint!.messages.length && <p className="p-4 text-sm text-muted-foreground">No recorded messages precede this step.</p>}</div></section>
        <aside className="min-w-0 space-y-4"><section className="rounded-lg border border-border p-4"><h2 className="mb-2 text-sm font-medium">Next recorded action</h2><p className="mb-2 text-xs text-muted-foreground">Step {selected.index + 1}, {selected.role}{selected.tool_name ? ` → ${selected.tool_name}` : ""}</p><pre className="whitespace-pre-wrap break-words font-sans text-sm">{selected.content}</pre>{selected.tool_input && <pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selected.tool_input, null, 2)}</pre>}</section><p className="text-xs text-muted-foreground">The action and later tool results are excluded from the context on the left. Download a checkpoint to inspect or reuse this recorded prefix. Executing tools from a checkpoint is not available yet.</p></aside>
      </div>}
    </>}
  </div>;
}
