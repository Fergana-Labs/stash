"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TracesPage";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { useConfirm } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import ImportTracesDialog from "@/components/reward-models/ImportTracesDialog";
import ConnectAgentDialog from "@/components/reward-models/ConnectAgentDialog";
import TraceDropzone from "@/components/reward-models/TraceDropzone";
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

function LatestTracesPage() {
  return (
    <Suspense fallback={<RmPageSkeleton />}>
      <Traces />
    </Suspense>
  );
}

function Traces() {
  useBreadcrumbs([{ label: "Traces" }], "reward-models");
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

  async function remove(targets: RmTraceSummary[]) {
    if (!targets.length || deleting) return;
    const ok = await confirm({
      title: targets.length === 1 ? `Delete "${targets[0].title}"?` : `Delete ${targets.length} traces?`,
      body: "Their steps, annotations, and scores will be deleted. This cannot be undone.",
      confirmLabel: targets.length === 1 ? "Delete" : `Delete ${targets.length} traces`,
    });
    if (!ok) return;
    setDeleting(targets.length === 1 ? targets[0].id : "bulk");
    const removed = new Set<string>();
    const failed = new Set<string>();
    try {
      // Bound concurrent requests and keep failed selections available for retry.
      for (let i = 0; i < targets.length; i += 5) {
        const batch = targets.slice(i, i + 5);
        const results = await Promise.allSettled(batch.map((trace) => rmDeleteTrace(trace.id)));
        results.forEach((result, index) => {
          if (result.status === "fulfilled") removed.add(batch[index].id);
          else failed.add(batch[index].id);
        });
      }
      setSelected((previous) => new Set([...previous, ...failed].filter((id) => !removed.has(id))));
      setTraces((previous) => previous?.filter((trace) => !removed.has(trace.id)) ?? null);
      if (removed.size) toast.success(`Deleted ${removed.size} trace${removed.size === 1 ? "" : "s"}`);
      if (failed.size) toast.error(`Couldn’t delete ${failed.size} trace${failed.size === 1 ? "" : "s"}. They remain selected so you can try again.`);
      await load();
    } finally {
      setDeleting(null);
    }
  }

  // Only ids that still exist count: a deleted trace from ?selected= must not be sent to training.
  const selectedIds = (traces ?? []).filter((t) => selected.has(t.id)).map((t) => t.id);
  const deletable = (traces ?? []).filter((t) => selected.has(t.id) && t.can_score !== false);
  const summary = summarizeSelection(traces ?? [], selected);

  return (
    <TraceDropzone onImported={() => void load()}>
      <RmPage
        wide
        title="Traces"
        actions={(
          <>
            <ConnectAgentDialog />
            <ImportTracesDialog onImported={() => void load()} />
          </>
        )}
      >
        {traces === null ? (
          <RmListSkeleton />
        ) : traces.length === 0 ? (
          <div className="py-24 text-center">
            <p className="m-0 text-[16px] font-medium text-foreground">Drop trace files or folders anywhere here</p>
            <p className="m-0 mt-2 text-[13px] text-muted-foreground">JSON, JSONL, or NDJSON. Or connect your agent to send runs automatically.</p>
          </div>
        ) : (
          <>
            {summary.count > 0 && (
              <div className="sticky top-0 z-20 -mx-3 mb-3 flex items-center gap-3 rounded-lg border border-brand-500/25 bg-background/95 px-3 py-2 shadow-sm backdrop-blur">
                <span className="text-[13px] font-medium text-foreground tabular-nums">
                  {summary.count} trace{summary.count === 1 ? "" : "s"} selected
                </span>
                <Button variant="ghost" size="sm" disabled={!!deleting} onClick={() => setSelected(new Set())}>
                  Clear
                </Button>
                <Button variant="destructive" size="sm" disabled={!!deleting || deletable.length === 0} onClick={() => void remove(deletable)}>
                  {deleting ? "Deleting…" : "Delete selected"}
                </Button>
                <span className="flex-1" />
                <div inert={!!deleting}>
                  <TrainPanel
                    traceIds={selectedIds}
                    summary={summary}
                    optionsPlacement="below"
                    onTrained={() => router.push("/reward-models/models")}
                  />
                </div>
              </div>
            )}
            <TraceTable
              traces={traces}
              selected={selected}
              onSelectedChange={setSelected}
              mode="browse"
              onDelete={(t) => void remove([t])}
              selectionDisabled={!!deleting}
              deletingId={deleting}
            />
          </>
        )}
      </RmPage>
    </TraceDropzone>
  );
}

export default function TracesPage() {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent />
    : <LatestTracesPage />;
}
