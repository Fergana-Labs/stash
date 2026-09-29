"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import ImportTracesDialog from "@/components/reward-models/ImportTracesDialog";
import ConnectAgentPanel from "@/components/reward-models/ConnectAgentPanel";
import TraceTable from "@/components/reward-models/TraceTable";
import TrainPanel from "@/components/reward-models/TrainPanel";
import { RmPage } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { RmListSkeleton, RmPageSkeleton } from "@/components/reward-models/RmSkeletons";
import { SELECTED_PARAM, summarizeSelection } from "@/components/reward-models/trace-selection";
import { rmDeleteTrace, rmListAllTraces } from "@/lib/api";
import type { RmTraceSummary } from "@/lib/types";

// New runs stream in over OpenTelemetry, so the list refreshes itself.
const POLL_MS = 5000;

export default function TracesPage() {
  return (
    <Suspense fallback={<RmPageSkeleton />}>
      <Traces />
    </Suspense>
  );
}

function Traces() {
  useBreadcrumbs([{ label: "Reward models" }], "reward-models");
  const router = useRouter();
  const searchParams = useSearchParams();
  const confirm = useConfirm();
  const [traces, setTraces] = useState<RmTraceSummary[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(searchParams.get(SELECTED_PARAM)?.split(",").filter((id) => id !== "") ?? []),
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  // Background refresh runs only after a successful load. A failure stops it,
  // so a down backend shows one toast instead of one every POLL_MS; the next
  // successful load (page visit, import, delete) turns it back on.
  const [polling, setPolling] = useState(false);

  const load = useCallback(async () => {
    try {
      setTraces(await rmListAllTraces());
      setPolling(true);
    } catch (e) {
      setPolling(false);
      toast.error(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, load]);

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
      const next = new Set(selected);
      next.delete(trace.id);
      setSelected(next);
      await load();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleting(null);
    }
  }

  // Only ids that still exist count: a deleted trace from ?selected= must not be sent to training.
  const selectedIds = (traces ?? []).filter((t) => selected.has(t.id)).map((t) => t.id);
  const summary = summarizeSelection(traces ?? [], selected);

  return (
    <RmPage
      title="Reward models"
      description="Annotate agent traces with + / − and comments, train a reward model on those labels, then use it to write skills for your agent."
      actions={<ImportTracesDialog onImported={() => void load()} />}
    >
      {traces !== null && <ConnectAgentPanel collapsible={traces.length > 0} />}
      {traces === null ? (
        <RmListSkeleton />
      ) : traces.length === 0 ? (
        <p className="m-0 text-center text-[12.5px] text-muted-foreground">Waiting for the first trace…</p>
      ) : (
        <>
          {summary.count > 0 && (
            <div className="sticky top-0 z-20 -mx-3 mb-3 flex items-center gap-3 rounded-lg border border-brand-500/25 bg-background/95 px-3 py-2 shadow-sm backdrop-blur">
              <span className="text-[13px] font-medium text-foreground tabular-nums">
                {summary.count} trace{summary.count === 1 ? "" : "s"} selected
              </span>
              <span className="text-[12.5px] text-muted-foreground">·</span>
              <span className="font-mono text-[12.5px] tabular-nums">
                <span className="text-green-700 dark:text-green-400">+{summary.positive}</span>{" "}
                <span className="text-red-600 dark:text-red-400">−{summary.negative}</span>{" "}
                <span className="font-sans text-muted-foreground">labels</span>
              </span>
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
              <span className="flex-1" />
              <TrainPanel
                traceIds={selectedIds}
                summary={summary}
                optionsPlacement="below"
                onTrained={() => router.push("/reward-models/models")}
              />
            </div>
          )}
          <TraceTable
            traces={traces}
            selected={selected}
            onSelectedChange={setSelected}
            mode="browse"
            onDelete={(t) => void remove(t)}
            deletingId={deleting}
          />
        </>
      )}
    </RmPage>
  );
}
