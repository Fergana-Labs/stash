"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import type { RmStep } from "@/lib/types";
import { wbAssess, wbAssessments, wbCreateFeedback, verdictOptions, type Assessment, type ChangeKind, type Verdict, type WorkbenchFeedback } from "@/lib/workbench-api";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, useWorkbenchLoad } from "./workbench-ui";

export default function AssessmentInspector({ traceId, steps, onJump, viewerId }: { traceId: string; steps: RmStep[]; onJump: (stepId: string) => void; viewerId?: string }) {
  const loader = useCallback(() => wbAssessments(traceId), [traceId]);
  const { data, loading, error, reload } = useWorkbenchLoad(loader, 5000);
  const [selectedId, setSelectedId] = useState<string | null>(() => typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("assessment"));
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const selected = data?.assessments.find((a) => a.id === selectedId) ?? data?.assessments[0];
  const completed = data?.assessments.filter((a) => a.status === "completed").length ?? 0;
  const failed = data?.coverage.failed ?? 0;

  async function assess() {
    setBusy(true); setActionError(null);
    try { await wbAssess(traceId); await reload(); }
    catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return <section aria-label="Automatic assessments" className="my-5 rounded-lg border border-border bg-surface/30">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
      <div><h2 className="m-0 text-[14px] font-medium">Assessments</h2><p className="m-0 mt-1 text-[11.5px] text-muted-foreground">{loading ? "Loading assessments…" : `${data?.coverage.assessed_actions ?? 0} / ${data?.coverage.total_actions ?? 0} actions assessed · ${completed} assessments${failed ? ` · ${failed} failed` : ""} · ${data?.coverage.pending ?? 0} pending`}</p></div>
      <div className="flex gap-2"><Button asChild variant="ghost" size="sm"><Link href="/reward-models/graders">Graders</Link></Button>{(!data?.owner_user_id || data.owner_user_id === viewerId) && <Button variant="outline" size="sm" disabled={busy} onClick={() => void assess()}>{busy ? "Scheduling…" : "Assess saved trace"}</Button>}</div>
    </div>
    <div className="p-4"><ErrorNotice error={error ?? actionError} onRetry={() => void reload()} />
      <ErrorNotice error={data?.coverage.last_error ?? null} />
      {data?.coverage.queue_status && <p className="mt-0 text-[11px] text-muted-foreground">Background queue: {data.coverage.queue_status}. Coverage counts recorded actions with at least one completed assessment; it is not a success rate.</p>}
      {!loading && !error && data?.assessments.length === 0 && <p className="m-0 text-[12.5px] text-muted-foreground">No assessment is recorded yet. <Link href="/reward-models/graders" className="underline">Configure a grader</Link> for automatic grading of incoming runs. Unassessed events have no verdict.</p>}
      {data && data.assessments.length > 0 && <div className="grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
        <div role="list" aria-label="Saved assessments" className="max-h-96 space-y-1 overflow-y-auto">
          {data.assessments.map((assessment) => <button key={assessment.id} type="button" role="listitem" aria-current={selected?.id === assessment.id ? "true" : undefined} onClick={() => setSelectedId(assessment.id)} className={`block w-full rounded-md border p-2.5 text-left ${selected?.id === assessment.id ? "border-brand-400/50 bg-brand-500/5" : "border-transparent hover:bg-surface"}`}>
            <span className="block text-[12px] font-medium">{assessment.criterion_name || assessment.criterion_id}</span>
            <span className="mt-1 flex flex-wrap items-center gap-1"><RecordBadge value={assessment.verdict ?? assessment.status} /><span className="text-[10px] text-muted-foreground">{relativeTime(assessment.created_at)}</span></span>
          </button>)}
        </div>
        {selected && <AssessmentDetail key={selected.id} assessment={selected} steps={steps} onJump={onJump} feedback={data.feedback?.filter((f) => f.assessment_id === selected.id)} />}
      </div>}
    </div>
  </section>;
}

export function AssessmentDetail({ assessment: a, steps, onJump, feedback = [] }: { assessment: Assessment; steps: RmStep[]; onJump: (stepId: string) => void; feedback?: WorkbenchFeedback[] }) {
  const stepMap = new Map(steps.map((step) => [step.id, step]));
  const snapshot = a.input_snapshot as { context_events?: { id: string }[]; omissions?: unknown[]; evidence_cutoff?: unknown; private_configuration_omitted?: boolean } | null;
  const contextIds = Array.isArray(snapshot?.context_events) ? snapshot.context_events.map((event) => event.id) : [];
  function eventLink(id: string, target = false) {
    const step = stepMap.get(id);
    return step ? <button type="button" onClick={() => onJump(id)} className="text-[12px] text-brand-600 underline underline-offset-2">{target ? "Target: " : ""}Step {step.index + 1} · {step.role}{step.tool_name ? ` · ${step.tool_name}` : ""}</button> : <span className="text-[12px] text-muted-foreground">Captured event {id} is unavailable</span>;
  }
  return <div className="min-w-0 space-y-3">
    <div className="flex flex-wrap items-center gap-2"><RecordBadge value={a.verdict ?? a.status} /><span className="text-[11px] text-muted-foreground">Grader version {a.grader_version_id}</span>{a.mode && <RecordBadge value={a.mode} />}</div>
    {a.target_step_id && eventLink(a.target_step_id, true)}
    {a.status === "failed" ? <ErrorNotice error={`Grading failed: ${a.error ?? "No error detail recorded"}. This is not a verdict on the agent.`} /> : <p className="m-0 whitespace-pre-wrap text-[13px] leading-relaxed">{a.reason ?? (a.status === "completed" ? "This grader returns a classification, without a written explanation. Inspect its exact input and raw output below." : "The grading request has not completed.")}</p>}
    {a.evidence_step_ids.length > 0 && <div><p className="m-0 mb-1 text-[11px] font-medium text-muted-foreground">Cited evidence</p><div className="flex flex-col items-start gap-1">{a.evidence_step_ids.map((id) => <span key={id}>{eventLink(id)}</span>)}</div></div>}
    {contextIds.length > 0 && <details><summary className="cursor-pointer text-[12px] text-dim">Selected context ({contextIds.length} events)</summary><p className="text-[11px] text-muted-foreground">These events were supplied to the grader. They are not model-generated citations.</p><div className="flex flex-col items-start gap-1">{contextIds.map((id) => <span key={id}>{eventLink(id)}</span>)}</div></details>}
    {snapshot?.omissions && snapshot.omissions.length > 0 && <p className="text-[12px] text-amber-700 dark:text-amber-400">Input contains {snapshot.omissions.length} recorded omission{snapshot.omissions.length === 1 ? "" : "s"}. Inspect the exact input to see missing or truncated content.</p>}
    {snapshot?.private_configuration_omitted && <p className="text-[12px] text-muted-foreground">This trace was shared for review. Private grader configuration is omitted from your view.</p>}
    <JsonDetails title={snapshot?.private_configuration_omitted ? "Saved grading input (private configuration omitted)" : "Exact saved grading input"} value={a.input_snapshot} />
    <JsonDetails title="Raw grading output" value={a.raw_output} />
    {a.usage != null && <JsonDetails title="Captured usage and cost" value={a.usage} />}
    {feedback.length > 0 && <div className="space-y-2 border-t border-border pt-3"><h3 className="m-0 text-[12px] font-medium">Subsequent corrections</h3><p className="m-0 text-[11px] text-muted-foreground">These comments were added after this assessment and were not part of its original input.</p>{feedback.map((f) => <div key={f.id} className="rounded-md bg-surface p-3"><p className="m-0 mb-2 whitespace-pre-wrap text-[12px]">{f.comment}</p><div className="flex flex-wrap items-center gap-2"><RecordBadge value={f.review_status} />{f.proposed_verdict && <span className="text-[11px] text-muted-foreground">{f.review_status === "accepted" ? "Reviewed" : "Proposed"} label: {f.proposed_verdict.replaceAll("_", " ")}</span>}<Link className="text-[11px] text-brand-600 underline" href={`/reward-models/review?feedback=${f.id}`}>Inspect correction</Link></div></div>)}</div>}
    <details className="border-t border-border pt-3"><summary className="cursor-pointer text-[12px] font-medium">Correct this assessment or agent behavior</summary><FeedbackForm assessment={a} /></details>
  </div>;
}

function FeedbackForm({ assessment }: { assessment: Assessment }) {
  const [comment, setComment] = useState("");
  const [verdict, setVerdict] = useState<Verdict | "">(assessment.verdict ?? "");
  const [kind, setKind] = useState<ChangeKind>("unclear");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await wbCreateFeedback({ trace_id: assessment.trace_id, assessment_id: assessment.id, ...(assessment.target_step_id ? { target_step_id: assessment.target_step_id } : {}), comment: comment.trim(), ...(verdict ? { proposed_verdict: verdict } : {}), change_kind: kind }); setSaved(true); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  if (saved) return <p role="status" className="text-[12px] text-muted-foreground">Correction saved. The original prediction is retained. <Link href="/reward-models/review" className="underline">Review the proposed interpretation</Link>.</p>;
  return <form onSubmit={(event) => void submit(event)} className="mt-3 space-y-3">
    <Field label="What was wrong?" hint="Cite the claim, tool result, or requirement. Your correction stays alongside the original prediction."><textarea required rows={3} value={comment} onChange={(e) => setComment(e.target.value)} className={inputClass} /></Field>
    <div className="grid gap-3 sm:grid-cols-2"><Field label="Correct verdict"><select value={verdict} onChange={(e) => setVerdict(e.target.value as Verdict | "")} className={inputClass}><option value="">No verdict proposed</option>{verdictOptions.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select></Field>
      <Field label="What needs to change?"><select value={kind} onChange={(e) => setKind(e.target.value as ChangeKind)} className={inputClass}><option value="unclear">Let Stash propose an interpretation</option><option value="judge_error">The grader missed a requirement</option><option value="agent_error">The agent made a mistake</option><option value="both">Both grader and agent</option><option value="requirement_change">A new requirement</option></select></Field></div>
    <ErrorNotice error={error} /><Button type="submit" size="sm" disabled={busy || !comment.trim()}>{busy ? "Saving…" : "Save correction"}</Button>
  </form>;
}
