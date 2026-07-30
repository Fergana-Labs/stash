"use client";

import { ExternalLink } from "lucide-react";

import type { MiniProgramManifest, TableRow } from "@/lib/types";

import { cellLabels, cellText, displayTimestamp } from "./cells";

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
  onToggleSelected: (range: boolean) => void;
  onOpen: () => void;
}) {
  const { detail } = manifest;
  const title = cellText(row, detail.title) || "Untitled";
  const subtitle = cellText(row, detail.subtitle);
  const badge = cellText(row, detail.badge);
  const timestamp = displayTimestamp(cellText(row, detail.timestamp));
  const body = cellText(row, detail.body);
  const labels = cellLabels(row, detail.labels);
  const link = cellText(row, detail.link);

  return (
    <article
      data-testid="app-card"
      className={`relative rounded-lg border bg-base ${
        selected || active ? "border-brand" : "border-border hover:border-muted-foreground/40"
      }`}
    >
      <input
        type="checkbox"
        checked={selected}
        onMouseDown={(event) => {
          event.preventDefault();
          onToggleSelected(event.shiftKey);
        }}
        onChange={() => undefined}
        aria-label={`Select ${title}`}
        className="absolute left-3 top-3 z-10 accent-[var(--brand)]"
      />

      <button
        type="button"
        onClick={onOpen}
        className="flex h-full w-full flex-col gap-2 p-4 pl-9 text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <span className="line-clamp-2 text-[14px] font-semibold leading-snug text-foreground">
            {title}
          </span>
          {badge && (
            <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
              {badge}
            </span>
          )}
        </div>

        {body ? (
          <p className="line-clamp-3 text-[12.5px] leading-relaxed text-muted-foreground">
            {body}
          </p>
        ) : pendingEnrichment ? (
          <p className="text-[12px] text-dim">Summary pending</p>
        ) : null}

        {labels.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {labels.map((label) => (
              <span
                key={label}
                className="rounded bg-raised px-1.5 py-0.5 text-[10.5px] text-foreground"
              >
                {label}
              </span>
            ))}
          </div>
        )}

        <div className="mt-auto flex items-center gap-2 pt-2 text-[11px] text-dim">
          {subtitle && (
            <span className="inline-flex min-w-0 items-center gap-1 truncate">
              {link && <ExternalLink className="h-3 w-3 shrink-0" />}
              {subtitle}
            </span>
          )}
          {subtitle && timestamp && <span aria-hidden>·</span>}
          {timestamp && <span className="shrink-0">{timestamp}</span>}
        </div>
      </button>
    </article>
  );
}
