"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronUp, Loader2 } from "lucide-react";
import {
  getImportBatch,
  listImportBatches,
  type ImportBatchDetail,
  type ImportBatchProgress,
} from "@/lib/api";

const POLL_MS = 60_000;

function isActive(batch: ImportBatchProgress): boolean {
  return batch.pending + batch.needs_client > 0;
}

/** Floating progress for bulk imports (extension bookmark/tab imports), which
 * can grind for days. Renders nothing unless a batch is actively importing —
 * then a fixed pill with live counts, expandable to per-batch detail
 * including which URLs were saved link-only and why. */
export default function ImportProgressPill() {
  const [batches, setBatches] = useState<ImportBatchProgress[]>([]);
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<ImportBatchDetail | null>(null);

  const refresh = useCallback(async () => {
    try {
      setBatches(await listImportBatches());
    } catch {
      // Progress is decorative; an auth blip must not error-loop the shell.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const active = batches.filter(isActive);
  if (active.length === 0) return null;

  const totals = active.reduce(
    (acc, b) => ({
      done: acc.done + b.done + b.link_only,
      total: acc.total + b.total,
    }),
    { done: 0, total: 0 },
  );

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
      {open && (
        <div className="w-[340px] rounded-xl border border-border bg-base p-4 shadow-xl">
          {active.map((b) => (
            <div key={b.id} className="mb-3 last:mb-0">
              <div className="text-[13px] font-medium text-foreground">
                {b.filename ?? (b.kind === "tabs" ? "Open tabs" : "Bookmarks import")}
              </div>
              <div className="mt-1 text-[12px] text-muted-foreground">
                {b.done} saved · {b.link_only} link-only · {b.pending} pending
                {b.needs_client > 0 && ` · ${b.needs_client} waiting for your browser extension`}
              </div>
              {b.link_only > 0 && (
                <button
                  type="button"
                  className="mt-1 cursor-pointer text-[11.5px] font-medium text-brand hover:underline"
                  onClick={() => {
                    if (detail?.id === b.id) {
                      setDetail(null);
                    } else {
                      void getImportBatch(b.id).then(setDetail);
                    }
                  }}
                >
                  {detail?.id === b.id ? "Hide link-only detail" : "Why are some link-only?"}
                </button>
              )}
              {detail?.id === b.id && (
                <ul className="scroll-thin mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-md border border-border bg-surface p-2">
                  {detail.failures.map((f) => (
                    <li key={f.url} className="text-[11px] leading-snug">
                      <span className="block truncate font-medium text-foreground">{f.url}</span>
                      <span className="text-muted-foreground">{f.error}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex cursor-pointer items-center gap-2 rounded-full border border-border bg-base px-3.5 py-2 text-[12.5px] font-medium text-foreground shadow-lg hover:bg-raised"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
        Importing · {totals.done.toLocaleString()}/{totals.total.toLocaleString()}
        <ChevronUp className={"h-3.5 w-3.5 text-muted-foreground transition-transform " + (open ? "rotate-180" : "")} />
      </button>
    </div>
  );
}
