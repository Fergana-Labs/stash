"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Flag, MessageSquare, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import ImportTracesDialog from "@/components/reward-models/ImportTracesDialog";
import { EmptyState, RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage, formatScore, relativeTime } from "@/components/reward-models/rm-text";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { rmDeleteTrace, rmListTraces } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";

const PAGE_SIZE = 50;

export default function TracesPage() {
  useBreadcrumbs([{ label: "Reward models" }], "reward-models");
  const confirm = useConfirm();
  const [page, setPage] = useState<{ traces: RmTraceSummary[]; total: number } | null>(null);
  const [offset, setOffset] = useState(0);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPage(await rmListTraces(PAGE_SIZE, offset));
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(trace: RmTraceSummary) {
    const ok = await confirm({
      title: `Delete "${trace.title}"?`,
      body: "Its steps, annotations, and scores are deleted. This cannot be undone.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
    setDeleting(trace.id);
    try {
      await rmDeleteTrace(trace.id);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <RmPage
      title="Reward models"
      description="Annotate agent traces with + / − and comments, train a reward model on those labels, then use it to optimize your agent's system prompt."
      actions={<ImportTracesDialog onImported={() => void load()} />}
    >
      {page === null ? (
        <RmListSkeleton />
      ) : page.total === 0 ? (
        <EmptyState title="No traces yet">
          Import traces from OpenAI, Anthropic, OpenTelemetry, Langfuse, LangSmith, Claude Code, or Codex to start
          annotating.
        </EmptyState>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full table-fixed border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-border bg-surface text-left text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  <th className="px-3 py-2 font-medium">Trace</th>
                  <th className="w-36 px-3 py-2 font-medium">Format</th>
                  <th className="w-16 px-3 py-2 text-right font-medium">Steps</th>
                  <th className="w-48 px-3 py-2 text-right font-medium">Labels</th>
                  <th className="w-24 px-3 py-2 text-right font-medium">Reward</th>
                  <th className="w-24 px-3 py-2 text-right font-medium">Imported</th>
                  <th className="w-10 px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {page.traces.map((trace) => (
                  <TraceRow
                    key={trace.id}
                    trace={trace}
                    deleting={deleting === trace.id}
                    onDelete={() => void remove(trace)}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <Pager offset={offset} total={page.total} onChange={setOffset} />
        </>
      )}
    </RmPage>
  );
}

function TraceRow({ trace, deleting, onDelete }: { trace: RmTraceSummary; deleting: boolean; onDelete: () => void }) {
  const href = `/reward-models/traces/${trace.id}`;
  return (
    <tr className="group border-b border-border-subtle last:border-b-0 hover:bg-surface/60">
      <td className="px-3 py-2.5">
        <Link href={href} className="block truncate font-medium text-foreground hover:text-brand-600">
          {trace.title}
        </Link>
        {trace.external_id && (
          <div className="truncate font-mono text-[11px] text-muted-foreground">{trace.external_id}</div>
        )}
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
      <td className="px-3 py-2.5 text-right text-[12px] whitespace-nowrap text-muted-foreground">
        {relativeTime(trace.created_at)}
      </td>
      <td className="px-2 py-2.5 text-right">
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
      </td>
    </tr>
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
      <span
        title="Comments"
        className={`inline-flex items-center gap-0.5 ${trace.comment_count ? "text-dim" : "text-muted-foreground/60"}`}
      >
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

function Pager({ offset, total, onChange }: { offset: number; total: number; onChange: (offset: number) => void }) {
  if (total <= PAGE_SIZE) {
    return <p className="mt-3 text-[12px] text-muted-foreground">{total} traces</p>;
  }
  const last = Math.min(offset + PAGE_SIZE, total);
  return (
    <div className="mt-3 flex items-center justify-between text-[12px] text-muted-foreground">
      <span>
        {offset + 1}–{last} of {total} traces
      </span>
      <div className="flex gap-1">
        <Button variant="outline" size="icon-sm" disabled={offset === 0} onClick={() => onChange(offset - PAGE_SIZE)} aria-label="Previous page">
          <ChevronLeft />
        </Button>
        <Button variant="outline" size="icon-sm" disabled={last >= total} onClick={() => onChange(offset + PAGE_SIZE)} aria-label="Next page">
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}
