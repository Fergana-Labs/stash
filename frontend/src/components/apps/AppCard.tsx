"use client";

import { ExternalLink, Sparkles } from "lucide-react";

import type { MiniProgramManifest, TableRow } from "@/lib/types";

import { cellText, cellLabels } from "./cells";

/** One row rendered as a card. Every slot is optional: a manifest only maps
 *  the columns its table actually has, and a freshly saved row has no
 *  enriched fields yet — which is why the summary slot has a pending state
 *  rather than collapsing the card's height as it fills in. */
export default function AppCard({
  row,
  manifest,
  pendingEnrichment,
  active,
  selected,
  onToggleSelected,
  onOpen,
}: {
  row: TableRow;
  manifest: MiniProgramManifest;
  pendingEnrichment: boolean;
  active: boolean;
  selected: boolean;
  onToggleSelected: () => void;
  onOpen: () => void;
}) {
  const { detail } = manifest;
  const title = cellText(row, detail.title) || "Untitled";
  const subtitle = cellText(row, detail.subtitle);
  const badge = cellText(row, detail.badge);
  const timestamp = cellText(row, detail.timestamp);
  const body = cellText(row, detail.body);
  const labels = cellLabels(row, detail.labels);
  const link = cellText(row, detail.link);

  return (
    // The checkbox can't live inside the clickable button, so the card is a
    // container with the open-action as its body and selection floated over it.
    <div
      data-testid="app-card"
      className={`group relative flex flex-col rounded-xl border transition-colors ${
        selected
          ? "border-brand bg-brand/5"
          : active
            ? "border-brand bg-brand/5"
            : "border-border bg-base hover:border-brand/40 hover:bg-raised"
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggleSelected}
        aria-label="Select item"
        data-testid="card-select"
        className={`absolute left-2.5 top-2.5 z-10 cursor-pointer accent-[var(--brand)] transition-opacity ${
          selected ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus:opacity-100"
        }`}
      />
      <button
        type="button"
        onClick={onOpen}
        className="flex cursor-pointer flex-col gap-2 p-4 pl-8 text-left"
      >
      <div className="flex items-start justify-between gap-3">
        <span className="line-clamp-2 text-[14px] font-semibold leading-snug text-foreground">
          {title}
        </span>
        {badge && (
          <span className="shrink-0 rounded-md bg-raised px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {badge}
          </span>
        )}
      </div>

      {body ? (
        <p className="line-clamp-3 text-[12.5px] leading-relaxed text-muted-foreground">{body}</p>
      ) : pendingEnrichment ? (
        <p className="flex items-center gap-1.5 text-[12.5px] italic text-dim">
          <Sparkles className="h-3 w-3 animate-pulse" />
          Summarising…
        </p>
      ) : null}

      {labels.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {labels.map((label) => (
            <span
              key={label}
              className="rounded-full bg-brand/10 px-2 py-0.5 text-[10.5px] font-medium text-brand"
            >
              {label}
            </span>
          ))}
        </div>
      )}

      <div className="mt-auto flex items-center gap-2 pt-1 text-[11px] text-dim">
        {subtitle && (
          <span className="inline-flex items-center gap-1 truncate">
            {link && <ExternalLink className="h-3 w-3 shrink-0" />}
            {subtitle}
          </span>
        )}
        {subtitle && timestamp && <span aria-hidden>·</span>}
        {timestamp && <span className="shrink-0">{timestamp}</span>}
      </div>
      </button>
    </div>
  );
}
