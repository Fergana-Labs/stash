import type { RmTraceDetail } from "@/lib/types";

/** Only the ordered recorded prefix is known, not the agent's exact live window. */
export function traceCheckpoint(trace: RmTraceDetail, stepId: string) {
  const ordered = [...trace.steps].sort((a, b) => a.index - b.index);
  const index = ordered.findIndex((step) => step.id === stepId);
  if (index < 0) throw new Error("Checkpoint step not found");
  const message = ({ id, index, role, content, tool_name, tool_input, tool_call_id }: RmTraceDetail["steps"][number]) => ({ id, index, role, content, tool_name, tool_input, tool_call_id });
  return { version: 1, kind: "recorded_trace_checkpoint", trace_id: trace.id, before_step_id: stepId,
    exact_context_window: false, messages: ordered.slice(0, index).map(message), next_action: message(ordered[index]) };
}
