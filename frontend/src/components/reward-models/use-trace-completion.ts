import { useEffect, useState } from "react";
import { rmEstimateCompletion, type RmTaskCompletion } from "@/lib/api";
import type { RmStep } from "@/lib/types";

export function useTraceCompletion(traceId: string, steps: RmStep[]) {
  // Polling the trace must not repeat inference, but edits and new events must.
  let hash = 2166136261;
  for (const step of steps) {
    const text = JSON.stringify([step.id, step.role, step.content, step.tool_name, step.tool_input]);
    for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  }
  const identity = `completion-v2:${traceId}:${steps.length}:${hash >>> 0}`;
  const enabled = steps.length > 0;
  const [result, setResult] = useState<{ identity: string; tasks: RmTaskCompletion[]; loading: boolean }>();
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    let failures = 0;
    async function load() {
      try {
        const response = await rmEstimateCompletion(traceId);
        if (cancelled) return;
        const pending = response.pending && ++attempts < 35;
        setResult({ identity, tasks: response.tasks, loading: pending });
        if (pending) timer = setTimeout(() => void load(), 3000);
        else if (response.unavailable && ++failures < 3) timer = setTimeout(() => void load(), 90000);
      } catch {
        if (!cancelled) {
          setResult({ identity, tasks: [], loading: false });
          if (++failures < 3) timer = setTimeout(() => void load(), 3000);
        }
      }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [traceId, identity, enabled]);
  return result?.identity === identity ? result : { tasks: [], loading: enabled };
}
