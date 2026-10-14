"use client";

import { useEffect, useRef, useState } from "react";
import { BehaviorChip } from "@/components/behaviors/behavior-ui";
import { stepWindow, traceBehaviorHits, type BehaviorHit } from "@/lib/behaviors-api";
import type { RmStep } from "@/lib/types";

/**
 * Behavior hits on this trace as chips; clicking one jumps to the first step of its window.
 * Also honors `?step=<index>` (links from the Behaviors page) by jumping there once the trace loads.
 */
export default function TraceBehaviorStrip({ traceId, steps, onReveal }: { traceId: string; steps: RmStep[]; onReveal: (stepId: string) => void }) {
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

  function jump(hit: BehaviorHit) {
    const step = steps.find((s) => s.index === hit.start_idx) ?? steps.find((s) => s.index >= hit.start_idx);
    if (step) onReveal(step.id);
  }

  if (!hits.length) return null;
  return <div aria-label="Behaviors" className="flex flex-wrap items-center gap-1.5 text-[11px]">
    <span className="mr-1 text-muted-foreground">Behaviors</span>
    {hits.map((hit) => <BehaviorChip key={hit.id} name={`${hit.behavior_name ?? "Behavior"} · ${stepWindow(hit.start_idx, hit.end_idx)}`} actor={hit.actor ?? "agent"}
      title={hit.evidence?.map((e) => `“${e.quote}”`).join("\n") || undefined} onClick={() => jump(hit)} />)}
  </div>;
}
