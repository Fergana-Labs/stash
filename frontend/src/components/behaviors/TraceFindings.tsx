"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, SearchCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BehaviorChip } from "@/components/behaviors/behavior-ui";
import { JudgeReports, headlineClass, judgeHeadline, useTraceJudge } from "@/components/agent-judge/TraceJudgePanel";
import { ACTOR_COLOR, traceBehaviorHits, type BehaviorHit } from "@/lib/behaviors-api";
import { cn } from "@/lib/utils";
import type { RmStep } from "@/lib/types";

/** "step 3" / "steps 3–5", numbered the way the viewer numbers steps. */
export function stepRange(start: number, end: number, numberOf: (index: number) => number) {
  const a = numberOf(start), b = numberOf(end);
  return a === b ? `step ${a}` : `steps ${a}–${b}`;
}

/** Behavior hit windows as colored ticks along the trace; hover names them, click jumps there. */
export function BehaviorMarks({ hits, total, selectedId, numberOf, onChoose }: {
  hits: BehaviorHit[]; total: number; selectedId: string | null; numberOf: (index: number) => number; onChoose: (hit: BehaviorHit) => void;
}) {
  if (!hits.length || !total) return <div className="h-3 flex-1" />;
  return <div role="group" aria-label="Behavior marks" className="relative h-3 min-w-0 flex-1 rounded-sm bg-muted/60">
    {hits.map((hit) => {
      const left = (hit.start_idx / total) * 100;
      const width = Math.max(0.6, ((hit.end_idx - hit.start_idx + 1) / total) * 100);
      const selected = hit.id === selectedId;
      return <button key={hit.id} type="button" onClick={() => onChoose(hit)} aria-label={`${hit.behavior_name ?? "Behavior"}, ${stepRange(hit.start_idx, hit.end_idx, numberOf)}`}
        title={`${hit.behavior_name ?? "Behavior"}, ${stepRange(hit.start_idx, hit.end_idx, numberOf)}`}
        className={cn("absolute inset-y-0 min-w-[3px] rounded-[2px] opacity-80 hover:opacity-100", selected && "opacity-100 ring-2 ring-foreground/60")}
        style={{ left: `${left}%`, width: `${width}%`, background: ACTOR_COLOR[hit.actor ?? "agent"].hex }} />;
    })}
  </div>;
}

/**
 * Findings on this trace in one collapsible section: behavior marks (a strip plus one chip per
 * behavior) and the Agent Judge's claims check. Honors `?step=<index>` by jumping there once.
 */
export default function TraceFindings({ traceId, steps, numberOf, onReveal, onJump, selectedId, onSelect }: {
  traceId: string;
  steps: RmStep[];
  numberOf: (index: number) => number;
  onReveal: (stepId: string) => void;
  onJump: (index: number) => void;
  selectedId: string | null;
  onSelect: (hit: BehaviorHit | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState<BehaviorHit[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const judge = useTraceJudge(traceId);
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
    const step = steps.find((s) => s.index === Number(param)) ?? steps.find((s) => s.index >= Number(param));
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

  // One chip per behavior (×count); clicking cycles through its windows.
  const byBehavior = new Map<string, BehaviorHit[]>();
  for (const h of [...hits].sort((a, b) => a.start_idx - b.start_idx)) byBehavior.set(h.behavior_id, [...(byBehavior.get(h.behavior_id) ?? []), h]);
  function cycle(windows: BehaviorHit[]) {
    const at = windows.findIndex((w) => w.id === selectedId);
    if (at === windows.length - 1) { onSelect(null); return; }
    choose(windows[at + 1]);
  }

  const reports = judge.reports ?? [];
  const latest = reports[0];
  const headline = latest ? judgeHeadline(latest) : null;
  const summary = [
    hits.length ? `${byBehavior.size} behavior${byBehavior.size === 1 ? "" : "s"}` : null,
  ].filter(Boolean).join(", ");

  async function check() {
    const id = await judge.check();
    if (id) { setReport(id); setOpen(true); }
  }

  return <section aria-label="Findings" className="text-[12px]">
    <div className="flex items-center gap-2.5">
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground">
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}Findings
      </button>
      <BehaviorMarks hits={hits} total={steps.length ? Math.max(...steps.map((s) => s.index)) + 1 : 0} selectedId={selectedId} numberOf={numberOf} onChoose={choose} />
      <span className="shrink-0 text-[11px] text-muted-foreground">{summary}{summary && headline ? ", " : ""}{headline && <span className={headlineClass(headline.tone)}>{headline.text}</span>}{!summary && !headline && "None yet"}</span>
      {judge.running && <Loader2 className="size-3 shrink-0 animate-spin text-muted-foreground" />}
      <Button size="xs" variant="outline" className="shrink-0" disabled={judge.starting || judge.running} onClick={() => void check()}><SearchCheck />{judge.starting ? "Starting…" : judge.running ? "Checking…" : "Check claims"}</Button>
      {judge.error && <span role="alert" className="text-[11px] text-destructive">{judge.error}</span>}
    </div>
    {open && <div className="scroll-thin mt-2 grid max-h-[45vh] gap-3 overflow-y-auto rounded-md border border-border bg-surface/30 p-2.5">
      <div>
        <h3 className="m-0 mb-1 text-[11px] font-semibold text-muted-foreground">Behaviors</h3>
        {byBehavior.size ? <div className="flex flex-wrap items-center gap-1.5">
          {[...byBehavior.values()].map((windows) => {
            const first = windows[0];
            const active = windows.some((w) => w.id === selectedId);
            return <span key={first.behavior_id} className={cn("rounded", active && "ring-1 ring-foreground/50")}>
              <BehaviorChip name={first.behavior_name ?? "Behavior"} actor={first.actor ?? "agent"} count={windows.length}
                title={windows.map((w) => stepRange(w.start_idx, w.end_idx, numberOf)).join(", ")} onClick={() => cycle(windows)} />
            </span>;
          })}
        </div> : <p className="m-0 text-[11.5px] text-muted-foreground">No behaviors tagged on this trace.</p>}
      </div>
      <div>
        <h3 className="m-0 mb-1 text-[11px] font-semibold text-muted-foreground">Claims check</h3>
        {!judge.reports ? <p role="status" className="m-0 text-[11.5px] text-muted-foreground">Loading…</p>
          : <JudgeReports reports={reports} selected={report ?? judge.latest} onSelect={setReport} steps={steps} numberOf={numberOf} onJump={onJump} />}
      </div>
    </div>}
  </section>;
}
