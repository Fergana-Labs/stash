"use client";

import { useEffect, useRef, useState } from "react";
import { BehaviorChip } from "@/components/behaviors/behavior-ui";
import { traceBehaviorHits, type BehaviorHit } from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";

/** "step 3" / "steps 3–5", numbered the way the viewer numbers steps. */
export function stepRange(start: number, end: number, numberOf: (index: number) => number) {
  const a = numberOf(start), b = numberOf(end);
  return a === b ? `step ${a}` : `steps ${a}–${b}`;
}

/**
 * Behavior hits on this trace as chips; clicking one selects it (the viewer tints its
 * steps) and jumps to its first step. Clicking the selected chip clears it.
 * Also honors `?step=<index>` (links from the Behaviors page) by jumping there once the trace loads.
 */
export default function TraceBehaviorStrip({ traceId, steps, numberOf, onReveal, selectedId, onSelect }: {
  traceId: string;
  steps: RmStep[];
  numberOf: (index: number) => number;
  onReveal: (stepId: string) => void;
  selectedId: string | null;
  onSelect: (hit: BehaviorHit | null) => void;
}) {
  const [hits, setHits] = useState<BehaviorHit[]>([]);
  const jumped = useRef(false);

  useEffect(() => {
    let cancelled = false;
    // Behaviors are an optional overlay: a trace still renders when they cannot load.
    traceBehaviorHits(traceId).then((r) => { if (!cancelled) setHits(r.hits.filter((h) => h.review !== "rejected")); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [traceId]);

  useEffect(() => {
    if (jumped.current || !steps.length) return;
    const param = new URLSearchParams(window.location.search).get("step");
    if (param === null || !/^\d+$/.test(param)) return;
    const step = steps.find((s) => s.index === Number(param));
    if (!step) return;
    jumped.current = true;
    onReveal(step.id);
  }, [steps, onReveal]);

  function choose(hit: BehaviorHit) {
    if (hit.id === selectedId) { onSelect(null); return; }
    onSelect(hit);
    const step = steps.find((s) => s.index === hit.start_idx) ?? steps.find((s) => s.index >= hit.start_idx);
    if (step) onReveal(step.id);
  }

  if (!hits.length) return null;
  return <div aria-label="Behaviors" className="flex flex-wrap items-center gap-1.5 text-[11px]">
    <span className="mr-1 text-muted-foreground">Behaviors</span>
    {hits.map((hit) => <span key={hit.id} className={cn("rounded", hit.id === selectedId && "ring-1 ring-brand-500")}>
      <BehaviorChip name={`${hit.behavior_name ?? "Behavior"} · ${stepRange(hit.start_idx, hit.end_idx, numberOf)}`} actor={hit.actor ?? "agent"}
        title={hit.evidence?.map((e) => `“${e.quote}”`).join("\n") || undefined} onClick={() => choose(hit)} />
    </span>)}
  </div>;
}
