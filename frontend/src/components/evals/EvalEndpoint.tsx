"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import AgentUsagePanel from "@/components/intuitions/AgentUsagePanel";
import type { OutputType } from "@/lib/intuition-api";
import { InlinePanel } from "./eval-ui";

const TRACE_EXAMPLE = { steps: [
  { index: 0, role: "user", content: "The customer's request or task" },
  { index: 1, role: "assistant", content: "The agent's response" },
] };

export default function EvalEndpoint({ id, outputType }: { id: string; outputType: OutputType }) {
  const [origin, setOrigin] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [exampleOpen, setExampleOpen] = useState(false);
  useEffect(() => setOrigin(window.location.origin), []);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  const endpoint = `${origin}/api/v1/intuitions/${id}/predict`;
  return <section aria-label="API endpoint" className="space-y-3">
    <div className="flex flex-wrap items-center gap-3 rounded border border-border bg-surface/30 px-3 py-2">
      <span className="text-[11px] font-medium text-muted-foreground">Connect</span>
      <span className="text-[11px] font-medium text-success">POST</span>
      <code className="min-w-0 flex-1 break-all text-[11px]">{endpoint}</code>
      <Button size="xs" variant="ghost" aria-label="Copy API endpoint" onClick={() => {
        setError("");
        void navigator.clipboard.writeText(endpoint).then(() => setCopied(true)).catch(() => setError("Could not copy. Select the endpoint to copy it manually."));
      }}>{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}</Button>
      <Button size="icon-xs" variant="ghost" className="text-muted-foreground hover:text-foreground" aria-label="API request details" title="API request details" aria-expanded={exampleOpen} aria-controls="api-request-example" onClick={() => setExampleOpen((open) => !open)}><Info /></Button>
    </div>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {exampleOpen && <div id="api-request-example"><InlinePanel title="API request" onClose={() => setExampleOpen(false)}><AgentUsagePanel standalone showDescription={false} modelId={id} outputType={outputType} sample={TRACE_EXAMPLE} /></InlinePanel></div>}
  </section>;
}
