"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { wbAssess, wbCreateFeedback, wbEvaluation, wbHistoricalEvaluation, type TraceEvaluation } from "@/lib/workbench-api";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, useWorkbenchLoad } from "./workbench-ui";

export default function TraceEvaluationPanel({ traceId, onJump, viewerId }: { traceId: string; onJump: (id: string) => void; viewerId?: string }) {
  const load = useCallback(() => wbEvaluation(traceId), [traceId]);
  const { data, error, reload } = useWorkbenchLoad(load, 5000);
  const [historical, setHistorical] = useState<TraceEvaluation | null>(null);
  const [historyId, setHistoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const selected = historyId ? historical : data?.current;
  async function retry() {
    setBusy(true); setActionError(null);
    try { await wbAssess(traceId); await reload(); } catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function selectVersion(id: string) {
    setHistoryId(id); setHistorical(null); setActionError(null);
    if (!id) return;
    setBusy(true);
    try { setHistorical(await wbHistoricalEvaluation(traceId, id)); } catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <section aria-label="Automatic Jev evaluation" className="mb-4 rounded-lg border border-border p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="m-0 text-[14px] font-medium">Trace success &amp; action credit</h2><span className="text-[11px] text-muted-foreground">Evaluated automatically by Jev</span></div>
    <p className="text-[12px] text-muted-foreground">Two fixed questions: was the trace successful, and how much did each action contribute? No grader setup is required.</p>
    <ErrorNotice error={error ?? actionError} onRetry={() => void reload()} />
    {data && !data.configured && <p role="status" className="text-[12px] text-amber-700 dark:text-amber-400">Jev is not connected on the server yet. Recorded traces will be evaluated after the connection is configured; no setup is required in your account.</p>}
    {data?.queue?.error && <ErrorNotice error={data.queue.error} />}
    {data && !data.current && !historyId && <p role="status" className="text-[12px] text-muted-foreground">{!data.boundary ? "Waiting for the agent to finish its response. Earlier evaluations are available in version history." : data.queue?.status === "failed" ? "Evaluation failed. This is not a failure verdict on the agent." : "Evaluation is queued for this recorded trace version. Success and action credit will appear here automatically."}</p>}
    {data && data.owner_user_id === viewerId && data.queue?.status === "failed" && <Button size="sm" variant="outline" disabled={busy} onClick={() => void retry()}>Retry evaluation</Button>}
    {!!data?.history.length && <div className="my-3"><Field label="Recorded trace version"><select value={historyId} disabled={busy} onChange={(event) => void selectVersion(event.target.value)} className={inputClass}><option value="">Current recorded trace</option>{data.history.map((version) => <option key={version.id} value={version.id}>Through step {version.boundary.step_index + 1} · {relativeTime(version.created_at)} · {version.status}</option>)}</select></Field></div>}
    {selected && <EvaluationResult key={selected.id} evaluation={selected} onJump={onJump} historical={!!historyId} />}
  </section>;
}

export function EvaluationResult({ evaluation: e, onJump, historical = false }: { evaluation: TraceEvaluation; onJump: (id: string) => void; historical?: boolean }) {
  const [callId, setCallId] = useState<string | null>(null);
  const [correctionTarget, setCorrectionTarget] = useState<string | null | undefined>(undefined);
  const call = e.calls.find((c) => c.id === callId);
  const creditByStep = new Map(e.credits.map((c) => [c.step_id, c]));
  const actionRows = e.actions;
  return <div className="space-y-3">
    {historical && <p className="text-[12px] text-amber-700 dark:text-amber-400">Saved evaluation of an earlier trace version. It does not describe any work recorded afterward.</p>}
    <p className="text-[11px] text-muted-foreground">Recorded through step {e.boundary.step_index + 1}. {e.boundary.kind === "inferred_response_boundary" ? "Completion is inferred from the last assistant response; session end was not recorded." : "The harness marked this response complete."} Later recorded work receives a new evaluation.</p>
    <div className="flex flex-wrap items-center gap-3"><strong className="text-[13px] font-medium">Was the trace successful?</strong><RecordBadge value={e.outcome ?? (e.status === "failed" ? "evaluation_failed" : "pending")} />{e.outcome_confidence != null && <span className="text-[11px] text-muted-foreground">Jev confidence: {(100 * e.outcome_confidence).toFixed(0)}%</span>}<Button variant="link" size="xs" onClick={() => setCallId(e.calls.find((c) => c.batch_index === 0 && c.status === "completed")?.id ?? e.calls.find((c) => c.batch_index === 0)?.id ?? null)}>Inspect saved evidence</Button></div>
    <ErrorNotice error={e.error} />
    <div><h3 className="m-0 text-[13px] font-medium">How much credit does each action deserve?</h3><p className="text-[11px] text-muted-foreground">{e.credited_actions} / {e.total_actions} actions evaluated. −2: major harm · −1: hindered · 0: neutral · +1: helped · +2: major contribution. Credit is an estimate using later results, separate from Jev’s confidence. Credits do not sum to 100%.</p></div>
    <div className="max-h-80 overflow-auto rounded-md border border-border"><table className="w-full text-left text-[12px]"><thead><tr className="border-b border-border"><th className="p-2">Action</th><th className="p-2">Estimated credit</th><th className="p-2">Confidence</th><th className="p-2">Evidence</th></tr></thead><tbody>{actionRows.map((step) => {
      const credit = creditByStep.get(step.id);
      return <tr key={step.id} className="border-b border-border last:border-0"><td className="max-w-64 p-2"><button className="text-left underline" onClick={() => onJump(step.id)}>Step {step.index + 1}{step.tool_name ? ` · ${step.tool_name}` : " · response"}</button>{step.content && <p className="mb-0 line-clamp-2 text-muted-foreground">{step.content}</p>}</td><td className="p-2">{credit ? credit.credit == null ? "Insufficient evidence" : `${credit.credit > 0 ? "+" : ""}${credit.credit} · ${credit.label.replaceAll("_", " ")}` : e.status === "failed" ? "Not evaluated" : "Pending"}</td><td className="p-2">{credit ? `${(credit.confidence * 100).toFixed(0)}%` : "—"}</td><td className="p-2"><div className="flex gap-2">{credit && <button className="underline" onClick={() => setCallId(credit.call_id)}>Inspect</button>}<button className="underline" onClick={() => setCorrectionTarget(step.id)}>Comment</button></div></td></tr>;
    })}</tbody></table></div>
    <Button variant="outline" size="sm" onClick={() => setCorrectionTarget(null)}>Comment on this evaluation</Button>
    {correctionTarget !== undefined && <EvaluationComment evaluation={e} targetId={correctionTarget} key={correctionTarget ?? "trace"} />}
    {call && <div className="space-y-2 rounded-md border border-border p-3"><h3 className="m-0 text-[12px] font-medium">Exact saved Jev request and response</h3>{!!call.input_snapshot.omissions?.length && <p className="text-[12px] text-amber-700 dark:text-amber-400">Some recorded context was omitted or truncated to fit Jev. The saved input lists every omission.</p>}<JsonDetails title="Saved input, fixed questions, and omissions" value={call.input_snapshot} open /><JsonDetails title="Raw Jev output" value={call.raw_output} /><ErrorNotice error={call.error} /></div>}
    <JsonDetails title="Evaluation version and all request attempts" value={e} />
  </div>;
}

function EvaluationComment({ evaluation, targetId }: { evaluation: TraceEvaluation; targetId: string | null }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await wbCreateFeedback({ trace_id: evaluation.trace_id, evaluation_id: evaluation.id, ...(targetId ? { target_step_id: targetId } : {}), comment, change_kind: "unclear" }); setSaved(true); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  if (saved) return <p role="status" className="text-[12px]">Comment saved with this trace version. <Link href="/reward-models/review" className="underline">Review its interpretation</Link>.</p>;
  return <form onSubmit={(event) => void submit(event)} className="space-y-2 rounded-md bg-surface p-3"><Field label="What should Stash learn from this?" hint="Describe an incorrect judgment, an agent mistake, or a requirement. The original evaluation is retained."><textarea required rows={3} value={comment} onChange={(event) => setComment(event.target.value)} className={inputClass} /></Field><ErrorNotice error={error} /><Button type="submit" size="sm" disabled={busy || !comment.trim()}>{busy ? "Saving…" : "Save comment"}</Button></form>;
}
