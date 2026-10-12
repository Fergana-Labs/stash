"use client";

import { useEffect, useState } from "react";
import { Check, ChevronRight, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Item, OutputType } from "@/lib/intuition-api";
import { Segmented } from "./im-ui";

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

const TOOLS: { name: string; when: string }[] = [
  { name: "stash_intuition_check", when: "Lint work before finishing. Pass model_ids, or a task description and the relevant models are picked for you. Returns passed, findings (flagged verdicts) and why." },
  { name: "stash_intuition_find", when: "Which of your models apply to a task, read from each model’s “when to use”, like picking skills." },
  { name: "stash_intuition_predict", when: "One verdict from one model, with confidence and the questions that drove it." },
  { name: "stash_intuition_batch", when: "Run a model over up to 200 items as an eval; with labels it reports accuracy, log loss and Brier." },
];

function curl(origin: string, path: string, body: unknown): string {
  return [
    `curl -X POST "${origin}/api/v1/intuitions${path}" \\`,
    `  -H "Authorization: Bearer $STASH_API_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${shellQuote(JSON.stringify(body))}'`,
  ].join("\n");
}

/** How an agent calls this model: the MCP tools and the REST endpoints behind them. */
export default function AgentUsagePanel({ modelId, outputType, sample, whenToUse }: { modelId: string; outputType: OutputType; sample: Item; whenToUse?: string }) {
  const [origin, setOrigin] = useState("https://your-stash-host");
  const [surface, setSurface] = useState<"mcp" | "rest">("mcp");
  useEffect(() => setOrigin(window.location.origin), []);
  const itemText = typeof sample === "string" ? sample : JSON.stringify(sample);
  const mcpCheck = JSON.stringify({ tool: "stash_intuition_check", arguments: { item: itemText, model_ids: [modelId] } }, null, 2);
  const mcpRouted = JSON.stringify({ tool: "stash_intuition_check", arguments: { item: itemText, task: "What the agent was asked to do" } }, null, 2);
  const mcpPredict = JSON.stringify({ tool: "stash_intuition_predict", arguments: { model_id: modelId, item: itemText } }, null, 2);
  const mcpBatch = JSON.stringify({ tool: "stash_intuition_batch", arguments: { model_id: modelId, items: [itemText, "…"], labels: [null, null] } }, null, 2);

  return (
    <details className="group rounded-lg border border-border bg-background">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium text-foreground select-none [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
        Use from an agent
        <span className="ml-2 text-[12px] font-normal text-muted-foreground">Agents consult it like a skill: check their work before finishing. Calls use the active version and land in the Inbox.</span>
      </summary>
      <div className="space-y-3 border-t border-border-subtle px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="m-0 max-w-2xl text-[12px] leading-relaxed text-muted-foreground">
            {whenToUse ? (
              <>
                Agents decide to consult this model from its <span className="text-foreground">when to use</span>: “{whenToUse.length > 160 ? `${whenToUse.slice(0, 160)}…` : whenToUse}”
              </>
            ) : (
              <>Add a “when to use” above so agents can find this model with stash_intuition_find or a routed check.</>
            )}
          </p>
          <Segmented
            size="xs"
            ariaLabel="Agent surface"
            value={surface}
            onChange={setSurface}
            options={[
              { value: "mcp", label: "MCP tools" },
              { value: "rest", label: "REST" },
            ]}
          />
        </div>
        {surface === "mcp" ? (
          <>
            <ul className="m-0 list-none divide-y divide-border-subtle rounded-md border border-border-subtle p-0">
              {TOOLS.map((t) => (
                <li key={t.name} className="grid gap-x-3 gap-y-0.5 px-3 py-1.5 sm:grid-cols-[13rem_minmax(0,1fr)]">
                  <code className="font-mono text-[11.5px] text-foreground">{t.name}</code>
                  <span className="text-[12px] leading-snug text-muted-foreground">{t.when}</span>
                </li>
              ))}
            </ul>
            <div className="grid gap-3 lg:grid-cols-2">
              <div className="min-w-0">
                <p className="m-0 mb-1.5 text-[12px] text-dim">Check with this model</p>
                <CopyBlock label="MCP check call" text={mcpCheck} />
              </div>
              <div className="min-w-0">
                <p className="m-0 mb-1.5 text-[12px] text-dim">Check, routed by task</p>
                <CopyBlock label="MCP routed check call" text={mcpRouted} />
              </div>
              <div className="min-w-0">
                <p className="m-0 mb-1.5 text-[12px] text-dim">Predict</p>
                <CopyBlock label="MCP predict call" text={mcpPredict} />
              </div>
              <div className="min-w-0">
                <p className="m-0 mb-1.5 text-[12px] text-dim">Batch eval</p>
                <CopyBlock label="MCP batch call" text={mcpBatch} />
              </div>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="m-0 mb-1.5 text-[12px] text-dim">
                POST <code className="font-mono text-foreground">/check</code> · lint an item with one or more models (or pass <code className="font-mono">task</code> instead of <code className="font-mono">model_ids</code>)
              </p>
              <CopyBlock label="check curl" text={curl(origin, "/check", { item: sample, model_ids: [modelId], caller: "my-agent" })} />
            </div>
            <div>
              <p className="m-0 mb-1.5 text-[12px] text-dim">POST <code className="font-mono text-foreground">/{"{id}"}/predict</code></p>
              <CopyBlock label="predict curl" text={curl(origin, `/${modelId}/predict`, { item: sample, caller: "my-agent" })} />
            </div>
            <div>
              <p className="m-0 mb-1.5 text-[12px] text-dim">
                POST <code className="font-mono text-foreground">/{"{id}"}/batch</code> · up to 200 items; labels optional
              </p>
              <CopyBlock label="batch curl" text={curl(origin, `/${modelId}/batch`, { items: [sample], labels: [null] })} />
            </div>
            {outputType === "preference" && (
              <div>
                <p className="m-0 mb-1.5 text-[12px] text-dim">POST <code className="font-mono text-foreground">/{"{id}"}/compare</code> · two items</p>
                <CopyBlock label="compare curl" text={curl(origin, `/${modelId}/compare`, { item_a: sample, item_b: sample, caller: "my-agent" })} />
              </div>
            )}
          </>
        )}
      </div>
    </details>
  );
}
