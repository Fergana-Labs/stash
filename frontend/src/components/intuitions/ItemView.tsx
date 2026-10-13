"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Item } from "@/lib/intuition-api";
import { fieldText } from "./im-helpers";

const LONG = 240;

/** Read-only rendering of an item: plain text, or one labeled block per object key. */
export default function ItemView({ item, clamp = true, className }: { item: Item; clamp?: boolean; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const image = typeof item === "object" && typeof item.data_url === "string" && /^data:image\/(png|jpeg|webp|gif);base64,/.test(item.data_url) ? item.data_url : null;
  const entries: [string | null, string][] = typeof item === "string" ? [[null, item]] : Object.entries(item).filter(([k]) => k !== "data_url").map(([k, v]) => [k, fieldText(v)]);
  const long = clamp && entries.some(([, text]) => text.length > LONG || text.split("\n").length > 4);
  const collapsed = long && !expanded;

  return (
    <div className={cn("min-w-0 space-y-1.5", className)}>
      {/* Inline data previews belong to the saved eval input. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {image && <img src={image} alt={typeof item === "object" && typeof item.name === "string" ? item.name : "Eval input"} className="max-h-64 max-w-full rounded-md border border-border object-contain" />}
      {entries.map(([key, text], i) => (
        <div key={key ?? i} className="min-w-0">
          {key !== null && <div className="mb-0.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">{key}</div>}
          <p className={cn("m-0 text-[12.5px] leading-relaxed break-words whitespace-pre-wrap text-foreground", collapsed && "line-clamp-3")}>
            {text || <span className="text-muted-foreground italic">empty</span>}
          </p>
        </div>
      ))}
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[11.5px] text-muted-foreground underline decoration-border underline-offset-2 hover:text-foreground"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}
