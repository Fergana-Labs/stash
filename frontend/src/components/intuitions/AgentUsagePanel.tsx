"use client";

import { useEffect, useState } from "react";
import { Check, ChevronRight, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Item, OutputType } from "@/lib/intuition-api";

function CopyBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="m-0 overflow-x-auto rounded-md border border-border-subtle bg-surface/70 p-3 pr-10 font-mono text-[11.5px] leading-relaxed text-foreground">{text}</pre>
      <Button
        variant="ghost"
        size="icon-xs"
        className="absolute top-2 right-2"
        aria-label={`Copy ${label}`}
        onClick={() => {
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </div>
  );
}

/** Escape for inclusion inside a single-quoted shell string. */
function shellQuote(text: string): string {
  return text.replace(/'/g, "'\\''");
}

/** How an agent calls this model: REST and the MCP tool. */
export default function AgentUsagePanel({ modelId, outputType, sample }: { modelId: string; outputType: OutputType; sample: Item }) {
  const [origin, setOrigin] = useState("https://your-stash-host");
  useEffect(() => setOrigin(window.location.origin), []);
  const predict = [
    `curl -X POST "${origin}/api/v1/intuitions/${modelId}/predict" \\`,
    `  -H "Authorization: Bearer $STASH_API_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${shellQuote(JSON.stringify({ item: sample, caller: "my-agent" }))}'`,
  ].join("\n");
  const compare = [
    `curl -X POST "${origin}/api/v1/intuitions/${modelId}/compare" \\`,
    `  -H "Authorization: Bearer $STASH_API_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${shellQuote(JSON.stringify({ item_a: sample, item_b: sample, caller: "my-agent" }))}'`,
  ].join("\n");
  const mcp = JSON.stringify({ tool: "stash_intuition_predict", arguments: { model_id: modelId, item: typeof sample === "string" ? sample : JSON.stringify(sample) } }, null, 2);

  return (
    <details className="group rounded-lg border border-border bg-background">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium text-foreground select-none [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
        Use from an agent
        <span className="ml-2 text-[12px] font-normal text-muted-foreground">Calls are served by the active version and land in the Inbox.</span>
      </summary>
      <div className="space-y-3 border-t border-border-subtle px-4 py-3">
        <div>
          <p className="m-0 mb-1.5 text-[12px] text-dim">REST · predict</p>
          <CopyBlock label="predict curl" text={predict} />
        </div>
        {outputType === "preference" && (
          <div>
            <p className="m-0 mb-1.5 text-[12px] text-dim">REST · compare two items</p>
            <CopyBlock label="compare curl" text={compare} />
          </div>
        )}
        <div>
          <p className="m-0 mb-1.5 text-[12px] text-dim">
            MCP tool <code className="font-mono text-foreground">stash_intuition_predict</code> with <code className="font-mono text-foreground">model_id</code>
          </p>
          <CopyBlock label="MCP call" text={mcp} />
        </div>
      </div>
    </details>
  );
}
