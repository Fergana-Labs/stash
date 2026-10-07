"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, RecordPanel } from "./workbench-ui";
import { wbRetryFeedback, wbReviewFeedback, verdictOptions, type ChangeKind, type Verdict, type WorkbenchFeedback } from "@/lib/workbench-api";

const changeKinds: { value: ChangeKind; label: string }[] = [
  { value: "unclear", label: "Ambiguous; needs interpretation" }, { value: "judge_error", label: "Grader missed an existing requirement" },
  { value: "agent_error", label: "Agent made a mistake" }, { value: "both", label: "Both grader and agent" }, { value: "requirement_change", label: "Requirement changed" },
  { value: "label_only", label: "Reviewed label only; no change requested" },
];

export default function FeedbackReview({ feedback: f, onReviewed }: { feedback: WorkbenchFeedback; onReviewed: () => Promise<void> }) {
  const [verdict, setVerdict] = useState<Verdict | "">(f.proposed_verdict ?? "");
  const [kind, setKind] = useState<ChangeKind>(f.change_kind);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function review(decision: "accept" | "reject") {
    setBusy(true); setError(null);
    try { await wbReviewFeedback(f.id, { decision, ...(verdict ? { proposed_verdict: verdict } : {}), change_kind: kind }); await onReviewed(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function retry() {
    setBusy(true); setError(null);
    try { await wbRetryFeedback(f.id); await onReviewed(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  const pending = f.review_status === "pending";
  const blockReason = f.interpretation && typeof f.interpretation === "object" && "instruction_draft_blocked_reason" in f.interpretation && typeof f.interpretation.instruction_draft_blocked_reason === "string" ? f.interpretation.instruction_draft_blocked_reason : null;
  return <RecordPanel title={<Link className="hover:underline" href={`/reward-models/traces/${f.trace_id}${f.target_step_id ? `#step-${f.target_step_id}` : ""}`}>Open source trace →</Link>} actions={<div className="flex items-center gap-2"><RecordBadge value={f.review_status} /><span className="text-[11px] text-muted-foreground">{relativeTime(f.created_at)}</span></div>}>
    <blockquote className="m-0 mb-3 border-l-2 border-brand-400/50 pl-3 text-[13px] leading-relaxed whitespace-pre-wrap">{f.comment}</blockquote>
    <p className="text-[11px] text-muted-foreground">{f.source ? `Source: ${f.source} · ` : ""}{f.change_kind === "label_only" ? "Explicit human review, saved separately from the original prediction." : "The original comment is retained. Acceptance records the reviewer’s judgment separately from model predictions."}</p>
    {blockReason && <p role="status" className="text-[12px] text-muted-foreground">{blockReason}</p>}
    {f.error && <ErrorNotice error={`Interpretation failed: ${f.error}`} />}
    {f.status === "failed" && pending && <Button variant="outline" size="sm" className="mb-3" disabled={busy} onClick={() => void retry()}>Retry interpretation</Button>}
    {f.status === "queued" || f.status === "running" ? <p role="status" className="text-[12px] text-muted-foreground">Preparing interpretation…</p> : <JsonDetails title={f.change_kind === "label_only" ? "Human review record" : "Interpretation and evidence"} value={f.interpretation} open />}
    {pending && <div className="mt-4 space-y-3"><div className="grid gap-3 sm:grid-cols-2"><Field label="Reviewed verdict"><select value={verdict} onChange={(e) => setVerdict(e.target.value as Verdict | "")} className={inputClass}><option value="">No verdict assigned</option>{verdictOptions.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select></Field><Field label="Reviewed interpretation"><select value={kind} onChange={(e) => setKind(e.target.value as ChangeKind)} className={inputClass}>{changeKinds.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select></Field></div>
      {kind === "requirement_change" && <p className="text-[12px] text-muted-foreground">A new requirement must be versioned. Historical labels under different requirements are not independent release evidence.</p>}
      <ErrorNotice error={error} /><div className="flex flex-wrap gap-2"><Button size="sm" disabled={busy || kind === "unclear" || f.status !== "completed"} onClick={() => void review("accept")}>{busy ? "Saving…" : kind === "label_only" ? "Save reviewed label without changes" : blockReason ? "Accept interpretation" : "Accept interpretation and prepare changes"}</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => void review("reject")}>Reject interpretation</Button></div>
    </div>}
    {f.review_status === "accepted" && <p className="mb-0 text-[12px] text-muted-foreground">{f.change_kind === "label_only" ? "Saved as reviewed evidence. No change was requested." : blockReason ? "Interpretation accepted. No instruction change was created because the repository scope is missing." : <><Link href="/reward-models/changes" className="underline">Inspect proposed changes</Link>. Release remains a separate action.</>}</p>}
    {f.changes && f.changes.length > 0 && <div className="mt-2 flex flex-col gap-1">{f.changes.map((change) => <Link key={change.id} href={`/reward-models/changes?change=${change.id}`} className="text-[12px] text-brand-600 underline">{change.title}</Link>)}</div>}
    {f.history && <div className="mt-3"><JsonDetails title="Feedback review and revision history" value={f.history} /></div>}
  </RecordPanel>;
}
