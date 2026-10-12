"use client";

import { useEffect, useState } from "react";
import { Check, ChevronRight, Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import SyntaxCode from "./SyntaxCode";

export default function TraceModelConnect({ modelId, traceId }: { modelId: string; traceId?: string }) {
  const [origin, setOrigin] = useState("https://api.joinstash.ai");
  const [copiedText, setCopiedText] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => setOrigin(window.location.origin), []);
  useEffect(() => {
    if (!copiedText) return;
    const timeout = setTimeout(() => setCopiedText(""), 1500);
    return () => clearTimeout(timeout);
  }, [copiedText]);
  const endpoint = "/api/v1/rm/traces/" + encodeURIComponent(traceId ?? "TRACE_ID") + "/score";
  const body = JSON.stringify({ reward_model_id: modelId }, null, 2).replace(/'/g, "'\\''");
  const text = [
    'curl -X POST "' + origin + endpoint + '" \\',
    '  -H "Authorization: Bearer $STASH_API_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    "  -d '" + body + "'",
  ].join("\n");
  return <details className="group">
    <summary className="flex cursor-pointer list-none items-center gap-1.5 py-3 text-[13px] font-medium [&::-webkit-details-marker]:hidden">
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />Connect
    </summary>
    <div className="pb-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex min-w-0 items-center gap-2"><span className="font-medium text-success">POST</span><code className="break-all font-mono">{endpoint}</code></div>
        <a href="https://joinstash.ai/docs/api" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">API reference<ExternalLink className="h-3 w-3" /></a>
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-3 py-1">
          <span className="text-xs text-muted-foreground">cURL</span>
          <Button variant="ghost" size="sm" aria-label="Copy API example" onClick={() => {
            void navigator.clipboard.writeText(text).then(() => { setCopiedText(text); setError(false); }).catch(() => setError(true));
          }}>{copiedText === text ? <Check /> : <Copy />}{copiedText === text ? "Copied" : "Copy"}</Button>
        </div>
        <div className="max-h-96 overflow-auto p-4"><SyntaxCode text={text} language="bash" /></div>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-destructive">Could not copy. Select the example to copy it manually.</p>}
    </div>
  </details>;
}
