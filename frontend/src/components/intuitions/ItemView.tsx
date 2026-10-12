"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Item } from "@/lib/intuition-api";
import { fieldProvenance, fieldText } from "./im-helpers";

const LONG = 240;

function isLong(text: string): boolean {
  return text.length > LONG || text.split("\n").length > 4;
}

function size(text: string): string {
  return text.length >= 1000 ? `${(text.length / 1000).toFixed(1)}k chars` : `${text.length} chars`;
}

const PROVENANCE = {
  agent: { label: "written by agent", className: "tag-agent", title: "The agent’s own account; treat its claims as claims." },
  environment: { label: "recorded by environment", className: "tag-muted", title: "Captured by the environment, independent of the agent." },
} as const;

/** One field: collapsed to a few lines when long; expanded fields scroll inside a fixed height. */
function Field({ name, text, clamp }: { name: string | null; text: string; clamp: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const long = isLong(text);
  const collapsed = clamp && long && !expanded;
  const provenance = name ? fieldProvenance(name) : null;
  return (
    <div className="min-w-0">
      {name !== null && (
        <div className="mb-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5">
          <span className="text-[10.5px] font-medium tracking-wide break-all text-muted-foreground uppercase">{name}</span>
          {provenance && (
            <span className={cn("tag normal-case", PROVENANCE[provenance].className)} title={PROVENANCE[provenance].title}>
              {PROVENANCE[provenance].label}
            </span>
          )}
          {long && <span className="font-mono text-[10.5px] text-muted-foreground/80">{size(text)}</span>}
        </div>
      )}
      <p
        className={cn(
          "m-0 text-[12.5px] leading-relaxed break-words whitespace-pre-wrap text-foreground",
          collapsed && "line-clamp-3",
          long && !collapsed && "scroll-thin max-h-80 overflow-y-auto rounded-md border border-border-subtle bg-surface/40 px-2.5 py-1.5",
        )}
      >
        {text || <span className="text-muted-foreground italic">empty</span>}
      </p>
      {clamp && long && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
          className="mt-0.5 text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

/**
 * Read-only rendering of an item: plain text, or one labeled section per object key.
 * Long fields collapse independently; agent_* / environment_* keys get a provenance tag.
 */
export default function ItemView({ item, clamp = true, className }: { item: Item; clamp?: boolean; className?: string }) {
  const entries: [string | null, string][] = typeof item === "string" ? [[null, item]] : Object.entries(item).map(([k, v]) => [k, fieldText(v)]);
  return (
    <div className={cn("min-w-0 space-y-2", className)}>
      {entries.map(([key, text], i) => (
        <Field key={key ?? i} name={key} text={text} clamp={clamp} />
      ))}
    </div>
  );
}
