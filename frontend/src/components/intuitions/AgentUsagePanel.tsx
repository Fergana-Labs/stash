"use client";

import { useEffect, useState } from "react";
import { Check, ChevronRight, Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import SyntaxCode from "@/components/reward-models/SyntaxCode";
import type { Item, OutputType } from "@/lib/intuition-api";

/** Escape for inclusion inside a single-quoted shell string. */
function shellQuote(text: string): string {
  return text.replace(/'/g, "'\\''");
}

export default function AgentUsagePanel({ modelId, outputType, sample }: { modelId: string; outputType: OutputType; sample: Item }) {
  const [origin, setOrigin] = useState("https://your-stash-host");
  const [example, setExample] = useState("curl");
  const [copiedText, setCopiedText] = useState("");
  const [copyError, setCopyError] = useState(false);
  useEffect(() => setOrigin(window.location.origin), []);
  useEffect(() => {
    if (!copiedText) return;
    const timeout = setTimeout(() => setCopiedText(""), 1500);
    return () => clearTimeout(timeout);
  }, [copiedText]);

  const comparing = outputType === "preference" && example === "compare";
  const endpoint = `/api/v1/intuitions/${modelId}/${comparing ? "compare" : "predict"}`;
  const payload = comparing ? { item_a: sample, item_b: sample, caller: "my-agent" } : { item: sample, caller: "my-agent" };
  const curl = [
    `curl -X POST "${origin}${endpoint}" \\`,
    '  -H "Authorization: Bearer $STASH_API_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    `  -d '${shellQuote(JSON.stringify(payload, null, 2))}'`,
  ].join("\n");
  const mcp = JSON.stringify({ tool: "stash_intuition_predict", arguments: { model_id: modelId, item: typeof sample === "string" ? sample : JSON.stringify(sample) } }, null, 2);
  const text = example === "mcp" ? mcp : curl;
  const examples = [{ id: "curl", label: "cURL" }, ...(outputType === "preference" ? [{ id: "compare", label: "Compare" }] : []), { id: "mcp", label: "MCP" }];

  return (
    <details className="group border-t border-border">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 py-3 text-[13px] font-medium text-foreground select-none [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
        API access
      </summary>
      <div className="pb-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 text-xs">
            <span className="font-medium text-success">{example === "mcp" ? "TOOL" : "POST"}</span>
            <code className="break-all font-mono text-foreground">{example === "mcp" ? "stash_intuition_predict" : endpoint}</code>
          </div>
          <a href="https://joinstash.ai/docs/api" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            API reference <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-3">
            <div className="flex gap-4" role="tablist" aria-label="API examples">
              {examples.map((tab) => (
                <button key={tab.id} type="button" role="tab" id={`api-${modelId}-${tab.id}`} aria-controls={`api-${modelId}-example`} aria-selected={example === tab.id} onClick={() => { setExample(tab.id); setCopyError(false); }} className={`border-b-2 py-2.5 text-xs transition-colors ${example === tab.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                  {tab.label}
                </button>
              ))}
            </div>
            <Button variant="ghost" size="sm" aria-label="Copy API example" onClick={() => {
              void navigator.clipboard.writeText(text).then(() => { setCopiedText(text); setCopyError(false); }).catch(() => setCopyError(true));
            }}>
              {copiedText === text ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
              {copiedText === text ? "Copied" : "Copy"}
            </Button>
          </div>
          <div role="tabpanel" id={`api-${modelId}-example`} aria-labelledby={`api-${modelId}-${example}`} className="max-h-96 overflow-auto p-4">
            <SyntaxCode text={text} language={example === "mcp" ? "json" : "bash"} />
          </div>
        </div>
        {copyError && <p role="alert" className="mt-2 text-xs text-destructive">Could not copy. Select the example to copy it manually.</p>}
      </div>
    </details>
  );
}
