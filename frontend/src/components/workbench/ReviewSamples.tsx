"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { verdictOptions, wbLabelAssessment, wbReviewSamples, type GraderCriterion, type ReviewSample, type Verdict } from "@/lib/workbench-api";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, useWorkbenchLoad } from "./workbench-ui";

export default function ReviewSamples({ onLabeled }: { onLabeled: () => Promise<void> }) {
  const { data, error, loading, reload } = useWorkbenchLoad(wbReviewSamples);
  return <section aria-label="Assessment audit sample" className="mb-6 rounded-lg border border-border p-4"><div className="flex items-start justify-between gap-3"><div><h2 className="m-0 text-[14px] font-medium">Audit recorded assessments</h2><p className="mb-0 mt-1 max-w-2xl text-[12px] text-muted-foreground">Review flagged findings and a representative sample. Labels supply independent evaluation examples without requesting a grader or instruction change.</p></div><Button variant="ghost" size="sm" onClick={() => void reload()}>Refresh sample</Button></div><ErrorNotice error={error} onRetry={() => void reload()} />{loading && <p className="text-[12px] text-muted-foreground">Loading review sample…</p>}{data?.length === 0 && <p className="mb-0 text-[12px] text-muted-foreground">No unreviewed completed assessments are available yet.</p>}<div className="mt-3 space-y-3">{data?.map((sample) => <SampleCard key={sample.assessment.id} sample={sample} onLabeled={async () => { await reload(); await onLabeled(); }} />)}</div></section>;
}

export function SampleCard({ sample, onLabeled }: { sample: ReviewSample; onLabeled: () => Promise<void> }) {
  const [verdict, setVerdict] = useState<Verdict | "">("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const a = sample.assessment;
  const snapshot = a.input_snapshot as { criteria?: GraderCriterion[]; context_events?: { id?: string; role: string; content: string; tool_name?: string; tool_input_text?: string }[]; omissions?: unknown[] } | null;
  const criterion = snapshot?.criteria?.find((item) => item.id === a.criterion_id);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!verdict) return;
    setBusy(true); setError(null);
    try { await wbLabelAssessment(a.id, verdict, comment.trim() || undefined); await onLabeled(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <details className="rounded-md border border-border p-3"><summary className="cursor-pointer text-[12px] font-medium">{a.criterion_name} · {sample.reason === "sample" ? "Representative sample" : sample.reason === "violation" ? "Flagged violation" : "Needs evidence review"}</summary><div className="mt-3 space-y-3"><div className="flex flex-wrap items-center gap-2"><span className="text-[11px] text-muted-foreground">Saved prediction:</span><RecordBadge value={a.verdict ?? a.status} /><Link className="text-[12px] text-brand-600 underline" href={`/reward-models/traces/${a.trace_id}?assessment=${a.id}${a.target_step_id ? `#step-${a.target_step_id}` : ""}`}>Inspect claim and context in trace</Link></div>
    {criterion && <p className="rounded-md bg-surface p-3 text-[12px]"><strong className="font-medium">Applicable requirement: </strong>{criterion.description}</p>}
    {snapshot?.context_events && <div className="max-h-80 overflow-y-auto rounded-md border border-border">{snapshot.context_events.map((event, index) => <div key={event.id ?? index} className="border-b border-border p-3 last:border-b-0"><div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground"><span>{event.role}{event.tool_name ? ` · ${event.tool_name}` : ""}</span>{event.id === a.target_step_id && <RecordBadge value="assessment_target" />}</div><p className="m-0 whitespace-pre-wrap break-words text-[12px] leading-relaxed">{event.content}</p>{event.tool_input_text && <pre className="mt-1 whitespace-pre-wrap break-words text-[11px] text-muted-foreground">{event.tool_input_text}</pre>}</div>)}</div>}
    {!!snapshot?.omissions?.length && <p className="text-[12px] text-amber-700 dark:text-amber-400">Some context was omitted or truncated. Inspect the saved input; choose insufficient evidence if the selected record does not support a verdict.</p>}
    <JsonDetails title="Full saved grading input and omissions" value={a.input_snapshot} /><form onSubmit={(event) => void save(event)} className="space-y-3"><Field label="Your reviewed verdict"><select required value={verdict} onChange={(event) => setVerdict(event.target.value as Verdict | "")} className={inputClass}><option value="">Choose after inspecting the evidence</option>{verdictOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></Field><Field label="Review note (optional)"><textarea rows={2} value={comment} onChange={(event) => setComment(event.target.value)} className={inputClass} /></Field><ErrorNotice error={error} /><Button type="submit" size="sm" disabled={busy || !verdict}>{busy ? "Saving…" : "Save reviewed label"}</Button><p className="m-0 text-[11px] text-muted-foreground">This saves a human label. The original prediction is retained. It does not draft or release a change.</p></form></div></details>;
}
