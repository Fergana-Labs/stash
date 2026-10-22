"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { Check, Copy, Info, Plug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { evalSurfaceClass, InlinePanel } from "@/components/evals/eval-ui";
import { traceConnectionCommands } from "./trace-connection";
import { traceActionClass } from "./rm-ui";
import SyntaxCode from "./SyntaxCode";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { usePublicApiBase } from "@/hooks/usePublicApiBase";
import { cn } from "@/lib/utils";

export default function ConnectAgentDialog() {
  const apiBase = usePublicApiBase();
  const [method, setMethod] = useState<"otel" | "http">("http");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [copiedText, setCopiedText] = useState("");
  const [error, setError] = useState("");
  const [sourceId, setSourceId] = useState("");
  const id = useId();
  const commands = traceConnectionCommands(apiBase, method, sourceId);
  const endpoint = `${apiBase}/api/v1/rm/traces/import`;
  useEffect(() => {
    if (!copiedText) return;
    const timer = setTimeout(() => setCopiedText(""), 1500);
    return () => clearTimeout(timer);
  }, [copiedText]);

  async function copy(text: string) {
    setError("");
    try { await navigator.clipboard.writeText(text); setCopiedText(text); }
    catch { setError("Could not copy. Select the text to copy it manually."); }
  }

  return <Dialog>
    <DialogTrigger asChild><Button size="xs" variant="outline" className={traceActionClass}><Plug />Connect your agent</Button></DialogTrigger>
    <DialogContent className={cn(evalSurfaceClass, "max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-[4px] sm:max-w-2xl")}>
      <DialogHeader>
        <DialogTitle className="text-sm">Connect your agent</DialogTitle>
        <DialogDescription className="text-xs">Send runs automatically. New traces appear here as they arrive.</DialogDescription>
      </DialogHeader>
      <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-surface/30 px-3 py-2">
        <span className="text-[11px] font-medium text-muted-foreground">Connect</span>
        <span className="text-[11px] font-medium text-success">POST</span>
        <code className="min-w-0 flex-1 break-all text-[11px]">{endpoint}</code>
        <Button size="xs" variant="ghost" aria-label="Copy trace endpoint" onClick={() => void copy(endpoint)}>{copiedText === endpoint ? <Check /> : <Copy />}{copiedText === endpoint ? "Copied" : "Copy"}</Button>
        <Button size="icon-xs" variant="ghost" aria-label="Trace request details" title="Trace request details" aria-expanded={detailsOpen} aria-controls={`${id}-details`} onClick={() => setDetailsOpen(!detailsOpen)}><Info /></Button>
      </div>
      {!detailsOpen && <p className="m-0 text-xs text-muted-foreground">Upload a completed run over HTTP, or stream spans with OpenTelemetry. <button type="button" className="text-foreground underline underline-offset-2" onClick={() => setDetailsOpen(true)}>View integration instructions</button></p>}
      {detailsOpen && <div id={`${id}-details`}><InlinePanel title="Integration instructions" onClose={() => setDetailsOpen(false)}>
        <div className="overflow-hidden rounded border border-border bg-background">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3">
            <div role="tablist" aria-label="Connection method" className="flex gap-4">
              {([["http", "HTTP API"], ["otel", "OpenTelemetry"]] as const).map(([value, label]) => <button key={value} type="button" role="tab" id={`${id}-${value}`} aria-controls={`${id}-example`} aria-selected={method === value} onClick={() => { setMethod(value); setError(""); }} className={cn("border-b-2 py-2.5 text-xs", method === value ? "border-foreground font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>{label}</button>)}
            </div>
            <Button size="xs" variant="ghost" aria-label="Copy integration example" onClick={() => void copy(commands)}>{copiedText === commands ? <Check /> : <Copy />}{copiedText === commands ? "Copied" : "Copy"}</Button>
          </div>
          <div role="tabpanel" id={`${id}-example`} aria-labelledby={`${id}-${method}`} className="space-y-3 p-3">
            <p className="m-0 text-xs leading-relaxed text-muted-foreground">{method === "http" ? "Send a completed run from your agent. This example uploads traces.jsonl; supported trace formats are detected automatically." : "For agents with OpenTelemetry or OpenInference instrumentation. Configure the OTLP exporter, then run your agent. Keep each run under one root span to preserve tool timing and subagent relationships."}</p>
            <div className="max-h-64 overflow-auto text-xs"><SyntaxCode text={commands} language="bash" /></div>
          </div>
        </div>
        <label className="grid gap-1.5 text-xs"><span className="font-medium">Source ID <span className="font-normal text-muted-foreground">(optional)</span></span><Input className="h-8 text-xs" value={sourceId} onChange={(event) => setSourceId(event.target.value)} placeholder="e.g. support-agent" maxLength={200} autoComplete="off" /><span className="text-[11px] text-muted-foreground">Use the same ID for each run. Name and filter it in Traces.</span></label>
      </InlinePanel></div>}
      {error && <p role="alert" className="m-0 text-xs text-destructive">{error}</p>}
      <div className="flex items-center justify-between gap-3 text-xs">
        <Link href="/settings#api-keys" className="text-brand-600 hover:underline">Create a Full access API key</Link>
        <a href="https://www.joinstash.ai/docs/api" target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground">Integration guide ↗</a>
      </div>
    </DialogContent>
  </Dialog>;
}
