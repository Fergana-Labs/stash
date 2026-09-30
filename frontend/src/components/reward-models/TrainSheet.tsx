"use client";

import { useEffect, useState } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { XIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { rmListAllTraces } from "@/lib/api";
import type { RmRewardModel, RmTraceSummary } from "@/lib/types";
import TraceTable from "./TraceTable";
import TrainPanel from "./TrainPanel";
import { RmListSkeleton } from "./RmSkeletons";
import { errorMessage } from "./rm-text";
import { summarizeSelection } from "./trace-selection";

/** Right-side sheet: pick traces (every trace preselected), then train on them. */
export default function TrainSheet({
  open,
  onOpenChange,
  onTrained,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onTrained: (model: RmRewardModel) => void;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/15 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(960px,92vw)] flex-col border-l border-border bg-background shadow-2xl outline-none data-open:animate-in data-open:slide-in-from-right data-closed:animate-out data-closed:slide-out-to-right">
          {/* Mounted only while open, so each opening starts from fresh traces and a fresh preselection. */}
          {open && <SheetBody onTrained={onTrained} />}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function SheetBody({ onTrained }: { onTrained: (model: RmRewardModel) => void }) {
  const [traces, setTraces] = useState<RmTraceSummary[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    rmListAllTraces()
      .then((all) => {
        setTraces(all);
        setSelected(new Set(all.map((t) => t.id)));
      })
      .catch((e) => toast.error(errorMessage(e)));
  }, []);

  const summary = summarizeSelection(traces ?? [], selected);
  const selectedIds = (traces ?? []).filter((t) => selected.has(t.id)).map((t) => t.id);

  return (
    <>
      <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
        <div>
          <DialogPrimitive.Title className="m-0 font-display text-[17px] font-semibold text-foreground">
            Create new reward model
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="m-0 mt-0.5 text-[12.5px] text-muted-foreground">
            We extract user feedback and assess response quality automatically. No manual annotations required.
          </DialogPrimitive.Description>
        </div>
        <DialogPrimitive.Close asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Close">
            <XIcon />
          </Button>
        </DialogPrimitive.Close>
      </div>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {traces === null ? (
          <RmListSkeleton />
        ) : (
          <TraceTable traces={traces} selected={selected} onSelectedChange={setSelected} mode="picker" />
        )}
      </div>

      <div className="flex items-center gap-4 border-t border-border bg-surface/60 px-6 py-3">
        <span className="text-[13px] text-foreground">
          Train on <span className="font-medium tabular-nums">{summary.count}</span> trace{summary.count === 1 ? "" : "s"}
        </span>
        <span className="flex-1" />
        <TrainPanel traceIds={selectedIds} summary={summary} optionsPlacement="above" onTrained={onTrained} />
      </div>
    </>
  );
}
