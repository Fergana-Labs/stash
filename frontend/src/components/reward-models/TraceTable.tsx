"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Flag, MessageSquare, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmTraceSummary } from "@/lib/types";
import { formatScore, relativeTime } from "./rm-text";
import { filterTraces, selectRange, toggleAllVisible, type TraceFilter } from "./trace-selection";

const FILTERS: { key: TraceFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "annotated", label: "Annotated" },
  { key: "unannotated", label: "Unannotated" },
];

/**
 * The trace list with filters, search, and multi-select (header checkbox,
 * shift-click ranges). "browse" is the Traces tab: titles link to the
 * annotation view and rows can be deleted. "picker" is the train sheet:
 * clicking anywhere on a row toggles it.
 */
export default function TraceTable({
  traces,
  selected,
  onSelectedChange,
  mode,
  onDelete,
  deletingId,
}: {
  traces: RmTraceSummary[];
  selected: Set<string>;
  onSelectedChange: (next: Set<string>) => void;
  mode: "browse" | "picker";
  onDelete?: (trace: RmTraceSummary) => void;
  deletingId?: string | null;
}) {
  const [filter, setFilter] = useState<TraceFilter>("all");
  const [query, setQuery] = useState("");
  // Index (in the visible list) of the last row clicked without shift: the anchor for shift-click ranges.
  const anchor = useRef<number | null>(null);

  const visible = filterTraces(traces, filter, query);
  const visibleIds = visible.map((t) => t.id);
  const selectedVisible = visibleIds.filter((id) => selected.has(id)).length;

  function toggleRow(index: number, shiftKey: boolean) {
    const id = visibleIds[index];
    const value = !selected.has(id);
    if (shiftKey && anchor.current !== null) {
      onSelectedChange(selectRange(visibleIds, selected, anchor.current, index, value));
    } else {
      onSelectedChange(selectRange(visibleIds, selected, index, index, value));
    }
    anchor.current = index;
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <div className="flex rounded-md border border-border p-0.5 text-[12px]">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => {
                setFilter(f.key);
                anchor.current = null;
              }}
              className={cn(
                "cursor-pointer rounded px-2.5 py-0.5 transition-colors",
                filter === f.key ? "bg-raised font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="flex h-7 w-64 items-center gap-1.5 rounded-md border border-border bg-background px-2 focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-400/20">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              anchor.current = null;
            }}
            placeholder="Search titles"
            className="min-w-0 flex-1 bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
        <span className="ml-auto text-[12px] text-muted-foreground tabular-nums">
          {visible.length === traces.length ? `${traces.length} traces` : `${visible.length} of ${traces.length} traces`}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full table-fixed border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-border bg-surface text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              <th className="w-10 py-2 pl-3">
                <Checkbox
                  checked={visible.length > 0 && selectedVisible === visible.length}
                  indeterminate={selectedVisible > 0 && selectedVisible < visible.length}
                  onClick={() => onSelectedChange(toggleAllVisible(visibleIds, selected))}
                  label="Select all shown traces"
                />
              </th>
              <th className="px-3 py-2 font-medium">Trace</th>
              <th className="w-32 px-3 py-2 font-medium">Format</th>
              <th className="w-16 px-3 py-2 text-right font-medium">Steps</th>
              <th className="w-44 px-3 py-2 text-right font-medium">Labels</th>
              <th className="w-24 px-3 py-2 text-right font-medium">Reward</th>
              <th className="w-24 px-3 py-2 text-right font-medium">Imported</th>
              {mode === "browse" && <th className="w-10 px-2 py-2" />}
            </tr>
          </thead>
          <tbody>
            {visible.map((trace, index) => (
              <TraceRow
                key={trace.id}
                trace={trace}
                mode={mode}
                checked={selected.has(trace.id)}
                onToggle={(e) => toggleRow(index, e.shiftKey)}
                deleting={deletingId === trace.id}
                onDelete={onDelete && (() => onDelete(trace))}
              />
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p className="m-0 px-3 py-6 text-center text-[12.5px] text-muted-foreground">No traces match.</p>
        )}
      </div>
    </div>
  );
}

function TraceRow({
  trace,
  mode,
  checked,
  onToggle,
  deleting,
  onDelete,
}: {
  trace: RmTraceSummary;
  mode: "browse" | "picker";
  checked: boolean;
  onToggle: (e: MouseEvent) => void;
  deleting: boolean;
  onDelete: (() => void) | undefined;
}) {
  const picker = mode === "picker";
  return (
    <tr
      onClick={picker ? onToggle : undefined}
      className={cn(
        "group border-b border-border-subtle select-none last:border-b-0",
        checked ? "bg-brand-500/[0.06] hover:bg-brand-500/10" : "hover:bg-surface/60",
        picker && "cursor-pointer",
      )}
    >
      <td className="py-2.5 pl-3" onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={checked} onClick={onToggle} label={`Select ${trace.title}`} />
      </td>
      <td className="px-3 py-2.5">
        {picker ? (
          <div className="truncate font-medium text-foreground">{trace.title}</div>
        ) : (
          <Link href={`/reward-models/traces/${trace.id}`} className="block truncate font-medium text-foreground hover:text-brand-600">
            {trace.title}
          </Link>
        )}
        {trace.external_id && <div className="truncate font-mono text-[11px] text-muted-foreground">{trace.external_id}</div>}
      </td>
      <td className="px-3 py-2.5">
        <span className="tag tag-muted">{trace.source_format}</span>
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-[12px] text-dim tabular-nums">{trace.step_count}</td>
      <td className="px-3 py-2.5">
        <LabelCounts trace={trace} />
      </td>
      <td className="px-3 py-2.5 text-right">
        {trace.latest_score ? (
          <span title={trace.latest_score.reward_model_name} className="font-mono text-[12px] text-foreground tabular-nums">
            {formatScore(trace.latest_score.score)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right text-[12px] whitespace-nowrap text-muted-foreground">{relativeTime(trace.created_at)}</td>
      {mode === "browse" && (
        <td className="px-2 py-2.5 text-right">
          {onDelete && (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={onDelete}
              disabled={deleting}
              aria-label="Delete trace"
              className="opacity-0 group-hover:opacity-100 hover:text-red-600 disabled:opacity-100"
            >
              <Trash2 />
            </Button>
          )}
        </td>
      )}
    </tr>
  );
}

function Checkbox({
  checked,
  indeterminate = false,
  onClick,
  label,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onClick: (e: MouseEvent) => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    ref.current!.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={() => {}}
      onClick={onClick}
      aria-label={label}
      className="size-3.5 cursor-pointer accent-brand-500"
    />
  );
}

function LabelCounts({ trace }: { trace: RmTraceSummary }) {
  return (
    <div className="flex items-center justify-end gap-2.5 font-mono text-[12px] tabular-nums">
      <span className={trace.positive_count ? "text-green-700 dark:text-green-400" : "text-muted-foreground/60"}>
        +{trace.positive_count}
      </span>
      <span className={trace.negative_count ? "text-red-600 dark:text-red-400" : "text-muted-foreground/60"}>
        −{trace.negative_count}
      </span>
      <span title="Comments" className={cn("inline-flex items-center gap-0.5", trace.comment_count ? "text-dim" : "text-muted-foreground/60")}>
        <MessageSquare className="h-3 w-3" />
        {trace.comment_count}
      </span>
      {trace.label_error_count > 0 && (
        <span title="Flagged label errors" className="inline-flex items-center gap-0.5 text-amber-600">
          <Flag className="h-3 w-3" />
          {trace.label_error_count}
        </span>
      )}
    </div>
  );
}
