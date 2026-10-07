"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmTraceSummary } from "@/lib/types";
import { formatScore, relativeTime } from "./rm-text";
import { searchTraces, selectRange, sortTraces, toggleAllVisible, type TraceSortKey, type TraceSortDirection } from "./trace-selection";

const COLUMNS: { key: TraceSortKey; label: string; className: string }[] = [
  { key: "title", label: "Trace", className: "" },
  { key: "steps", label: "Steps", className: "w-20 text-right" },
  { key: "comments", label: "Comments", className: "w-28 text-right" },
  { key: "credit", label: "Mean action credit", className: "w-40 text-right" },
  { key: "reward", label: "Latest score", className: "w-36 text-right" },
  { key: "imported", label: "Imported", className: "w-28 text-right" },
];

/**
 * The trace list with search, sorting, and multi-select (header checkbox,
 * shift-click ranges). "browse" is the Traces tab: rows open the
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
  const [query, setQuery] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("all");
  const [sort, setSort] = useState<{ key: TraceSortKey; direction: TraceSortDirection }>({ key: "imported", direction: "descending" });
  // Index (in the visible list) of the last row clicked without shift: the anchor for shift-click ranges.
  const anchor = useRef<number | null>(null);

  const filtered = searchTraces(traces, query).filter((trace) => assessmentFilter === "all"
    || (assessmentFilter === "violations" && (trace.workbench?.violations ?? 0) > 0)
    || (assessmentFilter === "failed" && ((trace.workbench?.failed ?? 0) > 0 || trace.workbench?.queue_status === "failed"))
    || (assessmentFilter === "pending" && ((trace.workbench?.pending ?? 0) > 0 || ["queued", "running"].includes(trace.workbench?.queue_status ?? ""))));
  const visible = sortTraces(filtered, sort.key, sort.direction);
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
      <div className="mb-3 flex flex-wrap items-center gap-3">
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
        {mode === "browse" && <select aria-label="Filter assessment status" value={assessmentFilter} onChange={(e) => { setAssessmentFilter(e.target.value); anchor.current = null; }} className="h-7 rounded-md border border-border bg-background px-2 text-[12px] text-muted-foreground"><option value="all">All assessment states</option><option value="violations">With criterion violations</option><option value="failed">Grading failures</option><option value="pending">Pending grading</option></select>}
        <span className="ml-auto text-[12px] text-muted-foreground tabular-nums">
          {visible.length === traces.length ? `${traces.length} traces` : `${visible.length} of ${traces.length} traces`}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className={cn("w-full table-fixed border-collapse text-[13px]", mode === "browse" && "min-w-[980px]")}>
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
              {COLUMNS.map((column) => (
                <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction : "none"} className={cn("px-3 py-2 font-medium", column.className)}>
                  <button
                    type="button"
                    className="cursor-pointer whitespace-nowrap hover:text-foreground"
                    title={`Sort by ${column.label.toLowerCase()}`}
                    onClick={() => {
                      setSort({ key: column.key, direction: sort.key === column.key && sort.direction === "ascending" ? "descending" : "ascending" });
                      anchor.current = null;
                    }}
                  >
                    {column.label}{sort.key === column.key && <span aria-hidden="true">{sort.direction === "ascending" ? " ↑" : " ↓"}</span>}
                  </button>
                </th>
              ))}
              {mode === "browse" && <th scope="col" className="w-44 px-3 py-2 text-right font-medium">Assessments</th>}
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
  const router = useRouter();
  const href = `/reward-models/traces/${trace.id}`;

  function openRow(event: MouseEvent) {
    if ((event.target as Element).closest("a, button, input")) return;
    if (picker) {
      onToggle(event);
      return;
    }
    if (event.metaKey || event.ctrlKey) {
      window.open(href, "_blank", "noopener,noreferrer");
      return;
    }
    router.push(href);
  }

  return (
    <tr
      onClick={openRow}
      className={cn(
        "group h-14 cursor-pointer border-b border-border-subtle select-none last:border-b-0",
        checked ? "bg-brand-500/[0.06] hover:bg-brand-500/10" : "hover:bg-surface/60",
      )}
    >
      <td className="py-2.5 pl-3" onClick={(e) => e.stopPropagation()}>
        <Checkbox checked={checked} onClick={onToggle} label={`Select ${trace.title}`} />
      </td>
      <td className="px-3 py-2.5">
        {picker ? (
          <div className="truncate font-medium text-foreground">{trace.title}</div>
        ) : (
          <Link href={href} className="block truncate font-medium text-foreground hover:text-brand-600">
            {trace.title}
          </Link>
        )}
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-[12px] text-dim tabular-nums">{trace.step_count}</td>
      <td className="px-3 py-2.5 text-right font-mono text-[12px] text-dim tabular-nums">{trace.comment_count}</td>
      <td className="px-3 py-2.5 text-right" title="Mean of the shared evaluator’s action rewards, not a whole-trace outcome score">
        {trace.action_credit ? <div className="leading-4">
          <span className="font-mono text-[12px] text-foreground tabular-nums">{formatScore(trace.action_credit.mean)}</span>
          <div className="text-[11px] text-muted-foreground">{trace.action_credit.count} actions · Stash v{trace.action_credit.revision}</div>
        </div> : <span className="text-muted-foreground">—</span>}
      </td>
      <td className="px-3 py-2.5 text-right">
        {trace.latest_score ? (
          <div className="leading-4">
            <span className="font-mono text-[12px] text-foreground tabular-nums">{formatScore(trace.latest_score.score)}</span>
            <div className="truncate text-[11px] text-muted-foreground" title={trace.latest_score.reward_model_name}>{trace.latest_score.reward_model_name}</div>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-2.5 text-right text-[12px] whitespace-nowrap text-muted-foreground">{relativeTime(trace.created_at)}</td>
      {mode === "browse" && <td className="px-3 py-2.5 text-right text-[11px]" title="Coverage counts actions with any completed assessment. Violations use the active grader’s latest assessment; grading failures are not agent violations.">
        {trace.workbench ? <div className="space-y-0.5"><div className="text-dim tabular-nums">{trace.workbench.assessed_actions} / {trace.workbench.total_actions} actions assessed</div>
          {trace.workbench.violations > 0 && <div className="text-red-700 dark:text-red-400">{trace.workbench.violations} criterion violation{trace.workbench.violations === 1 ? "" : "s"}</div>}
          {(trace.workbench.failed > 0 || trace.workbench.queue_status === "failed") && <div className="text-amber-700 dark:text-amber-400">Grading failed{trace.workbench.failed > 0 ? ` (${trace.workbench.failed})` : ""}</div>}
          {(trace.workbench.pending > 0 || ["queued", "running"].includes(trace.workbench.queue_status ?? "")) && <div className="text-muted-foreground">{trace.workbench.pending > 0 ? `${trace.workbench.pending} pending` : "Grading queued"}</div>}
        </div> : <span className="text-muted-foreground">Not assessed</span>}
      </td>}
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
