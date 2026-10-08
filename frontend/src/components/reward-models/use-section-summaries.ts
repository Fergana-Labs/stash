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
    const text = JSON.stringify([step.id, step.role, step.content, step.tool_name, step.tool_input]);
    for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  }
  return `section-assessment-v3:${range(node).first_step_id}:${range(node).last_step_id}:${hash >>> 0}`;
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
    setStatus("loading");
    async function load() {
      try {
        const result = await rmSummarizeSections(traceId, missing.map(({ first_step_id, last_step_id }) => ({ first_step_id, last_step_id })));
        if (cancelled) return;
        for (const copy of result.sections) {
          const request = missing.find((item) => item.first_step_id === copy.first_step_id && item.last_step_id === copy.last_step_id);
          if (request) cache.current.set(request.identity, copy);
        }
        refresh((value) => value + 1);
        if (result.pending && ++attempts < 35) timer = setTimeout(() => void load(), 3000);
        else setStatus(result.unavailable || result.pending ? "unavailable" : "ready");
      } catch { if (!cancelled) setStatus("unavailable"); }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [traceId, signature]);
  // State revision publishes the ref cache after a request finishes.
  void revision;
  return { copy: (node: TraceGroup) => cache.current.get(identity(node)), status };
}
