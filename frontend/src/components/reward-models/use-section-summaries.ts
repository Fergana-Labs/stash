import { useEffect, useRef, useState } from "react";
import { rmSummarizeSections, type RmSectionCopy } from "@/lib/api";
import type { TraceGroup } from "./trace-outline";
import { rowSteps } from "./trace-rows";

function range(node: TraceGroup) {
  return { first_step_id: rowSteps(node.rows[0])[0].id, last_step_id: rowSteps(node.rows.at(-1)!).at(-1)!.id };
}

function identity(node: TraceGroup): string {
  // Invalidate edited content as well as growing ranges; polling identical data
  // must never trigger another generation request.
  let hash = 2166136261;
  for (const row of node.rows) for (const step of rowSteps(row)) {
    const text = JSON.stringify([step.id, step.role, step.content, step.tool_name, step.tool_input, step.metadata?.thinking]);
    for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  }
  return `section-assessment-v4:${range(node).first_step_id}:${range(node).last_step_id}:${hash >>> 0}`;
}

export function useSectionSummaries(traceId: string, nodes: TraceGroup[]) {
  const cache = useRef(new Map<string, RmSectionCopy>());
  const [revision, refresh] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const signature = JSON.stringify(nodes.map((node) => ({ identity: identity(node), ...range(node) })));
  useEffect(() => {
    const requested = JSON.parse(signature) as ({ identity: string } & ReturnType<typeof range>)[];
    const missing = requested.filter((item) => !cache.current.has(item.identity));
    if (!missing.length) { setStatus("ready"); return; }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const failed = new Set<string>();
    setStatus("loading");
    async function load() {
      const remaining = missing.filter((item) => !cache.current.has(item.identity) && !failed.has(item.identity));
      const batches = Array.from({ length: Math.ceil(remaining.length / 4) }, (_, i) => remaining.slice(i * 4, (i + 1) * 4));
      // Four is only an API batch size. Keep arbitrary-length task lists and
      // publish each batch as it arrives, with at most two requests in flight.
      for (let i = 0; i < batches.length && !cancelled; i += 2) {
        await Promise.all(batches.slice(i, i + 2).map(async (batch) => {
          try {
            const result = await rmSummarizeSections(traceId, batch.map(({ first_step_id, last_step_id }) => ({ first_step_id, last_step_id })));
            for (const copy of result.sections) {
              const request = batch.find((item) => item.first_step_id === copy.first_step_id && item.last_step_id === copy.last_step_id);
              if (request) cache.current.set(request.identity, copy);
            }
            if (result.unavailable) for (const item of batch) if (!cache.current.has(item.identity)) failed.add(item.identity);
          } catch { for (const item of batch) failed.add(item.identity); }
          if (!cancelled) refresh((value) => value + 1);
        }));
      }
      if (cancelled) return;
      const pending = missing.some((item) => !cache.current.has(item.identity) && !failed.has(item.identity));
      if (pending && ++attempts < 35) timer = setTimeout(() => void load(), 3000);
      else setStatus(failed.size || pending ? "unavailable" : "ready");
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [traceId, signature]);
  // State revision publishes the ref cache after a request finishes.
  void revision;
  return { copy: (node: TraceGroup) => cache.current.get(identity(node)), status };
}
