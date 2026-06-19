"use client";

import { useEffect, useRef, useState } from "react";

import { listCanvases } from "@/lib/api";
import type { Canvas } from "@/lib/types";

// Reopen a saved canvas. Canvases persist as workspace objects, but the panel
// otherwise only opens via a live chat turn — this is the way back to one the
// agent built earlier. Lists most-recent-first and opens the chosen one into
// the active chat's panel.
export default function CanvasPicker({
  workspaceId,
  onSelect,
}: {
  workspaceId: string;
  onSelect: (canvasId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [canvases, setCanvases] = useState<Canvas[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Fetch fresh each time it's opened so newly built canvases show up.
  useEffect(() => {
    if (!open) return;
    setCanvases(null);
    listCanvases(workspaceId)
      .then((r) => setCanvases(r.canvases))
      .catch(() => setCanvases([]));
  }, [open, workspaceId]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="shrink-0 rounded-md border border-border px-3 py-1.5 text-[12.5px] font-medium text-dim hover:border-[var(--color-brand-300)] hover:bg-surface hover:text-foreground"
      >
        Canvases
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 overflow-hidden rounded-md border border-border bg-base shadow-lg">
          <div className="max-h-80 overflow-y-auto py-1">
            {canvases === null ? (
              <div className="px-3 py-2 text-[12.5px] text-muted">Loading…</div>
            ) : canvases.length === 0 ? (
              <div className="px-3 py-2 text-[12.5px] text-muted">
                No canvases yet. Ask the agent to build one.
              </div>
            ) : (
              canvases.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => {
                    onSelect(c.id);
                    setOpen(false);
                  }}
                  className="block w-full cursor-pointer px-3 py-2 text-left hover:bg-surface"
                >
                  <div className="truncate text-[13px] font-medium text-foreground">{c.title}</div>
                  <div className="text-[11px] text-muted">
                    {new Date(c.updated_at).toLocaleString()}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
