"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage, relativeTime } from "@/components/reward-models/rm-text";
import GraderConfigEditor, { validGraderConfig } from "./GraderConfigEditor";
import ContentDiff from "./ContentDiff";
import { ErrorNotice, inputClass, JsonDetails, RecordBadge, useWorkbenchLoad } from "./workbench-ui";
import { wbCheckChange, wbEditChange, wbInstructionReleases, wbRejectChange, wbReleaseChange, wbRollbackInstruction, type WorkbenchChange } from "@/lib/workbench-api";

export default function ChangeEditor({ change, onChanged }: { change: WorkbenchChange; onChanged: () => Promise<void> }) {
  const [content, setContent] = useState(change.content);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acceptUnmeasured, setAcceptUnmeasured] = useState(false);
  const editable = !["released", "rejected", "checking"].includes(change.status);
  const dirty = JSON.stringify(content) !== JSON.stringify(change.content);
  const valid = change.kind === "grader" ? !!content.config && validGraderConfig(content.config) : !!content.text?.trim();
  const newRequirement = change.kind === "grader" && change.check_report?.can_accept_unmeasured === true;
  const releasable = change.check_report?.passed === true || (newRequirement && acceptUnmeasured);
  async function action(name: string, operation: () => Promise<unknown>) {
    setBusy(name); setError(null);
    try { await operation(); await onChanged(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(null); }
  }
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-3 text-[12px] text-muted-foreground">{change.feedback_id && <Link href={`/reward-models/review?feedback=${change.feedback_id}`} className="underline">Source reviewed correction</Link>}{change.scope && <span>Scope: {change.scope.repository ?? "All repositories"} · {change.scope.source_format ?? "All harnesses"}</span>}{change.parent_version_id && <span>Parent version: {change.parent_version_id}</span>}</div>
    {change.scope && <p className="text-[12px] text-muted-foreground">Scope: {change.scope.repository || "all repositories"} · {change.scope.source_format || "all captured harnesses"}</p>}
    {change.previous_content && <JsonDetails title="Previous released content" value={change.previous_content.text ?? change.previous_content.config} />}
    {change.previous_content && <ContentDiff before={change.previous_content.text ?? JSON.stringify(change.previous_content.config, null, 2)} after={content.text ?? JSON.stringify(content.config, null, 2)} />}
    {change.kind === "grader" && content.config ? <GraderConfigEditor value={content.config} onChange={(config) => setContent({ ...content, config })} disabled={!editable || !!busy} /> : <Field label="Exact agent instructions" hint="Draft text is not sent to agents. Release makes a specific version available; a load receipt is separate."><textarea value={content.text ?? ""} onChange={(e) => setContent({ ...content, text: e.target.value })} rows={8} disabled={!editable || !!busy} className={`${inputClass} font-mono text-[12px]`} /></Field>}
    {dirty && <div className="space-y-2"><p className="m-0 text-[12px] text-muted-foreground">Unsaved edits invalidate earlier checks. Save the text, then check it again.</p><Button size="sm" disabled={!!busy || !valid} onClick={() => void action("save", () => wbEditChange(change.id, content))}>{busy === "save" ? "Saving…" : "Save draft"}</Button></div>}
    <ChangeReport report={change.check_report} kind={change.kind} />
    {newRequirement && editable && <label className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-[12px]"><input type="checkbox" checked={acceptUnmeasured} disabled={!!busy || dirty} onChange={(event) => setAcceptUnmeasured(event.target.checked)} className="mt-0.5" /><span>I confirm this is a new requirement. Grader accuracy under this requirement is unmeasured; historical labels under a different requirement do not validate it.</span></label>}
    <ErrorNotice error={error ?? change.error ?? null} />
    {editable && <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={!!busy || dirty || !valid} onClick={() => void action("check", () => wbCheckChange(change.id))}>{busy === "check" ? "Checking…" : "Check saved change"}</Button><Button size="sm" disabled={!!busy || dirty || change.status !== "checked" || !releasable} onClick={() => void action("release", () => wbReleaseChange(change.id, newRequirement && acceptUnmeasured))}>{busy === "release" ? "Releasing…" : newRequirement ? "Activate new requirement (unmeasured)" : change.kind === "grader" ? "Release grader version" : "Release for agent use"}</Button><Button size="sm" variant="ghost" disabled={!!busy} onClick={() => void action("reject", () => wbRejectChange(change.id))}>Reject change</Button></div>}
    {change.status === "checking" && <p role="status" className="text-[12px] text-muted-foreground">Checks are running. Grader checks read saved records; they do not re-execute agent tool calls.</p>}
    {change.history && <JsonDetails title="Change checks, revisions, and release history" value={change.history} />}
    {change.kind === "instruction" && change.grader_id && <InstructionHistory graderId={change.grader_id} onChanged={onChanged} />}
    {change.kind === "instruction" && <div className="rounded-md border border-border p-3"><h3 className="m-0 text-[12px] font-medium">Later-run delivery evidence</h3>{change.delivery_records?.length ? <div className="mt-2 space-y-3">{change.delivery_records.map((receipt) => <div key={receipt.id} className="space-y-1 text-[12px]"><div className="flex flex-wrap items-center gap-2">{receipt.trace_id ? <Link className="underline" href={`/reward-models/traces/${receipt.trace_id}${receipt.step_id ? `#step-${receipt.step_id}` : ""}`}>Open captured run</Link> : <span>Session {receipt.session_id}</span>}<RecordBadge value={receipt.status} /><span className="text-muted-foreground">{relativeTime(receipt.captured_at ?? receipt.offered_at)}</span></div><p className="m-0 text-muted-foreground">{receipt.status === "captured" ? "Exact released instructions were found in the run’s recorded context." : "Instructions were offered to the harness. Loading into the agent’s context is unconfirmed."}</p><JsonDetails title="Exact instruction delivery record" value={receipt} /></div>)}</div> : <p className="mb-0 text-[12px] text-muted-foreground">No run has a recorded load receipt for this change. {change.status === "released" ? "Release establishes availability, not that an agent received or followed it." : "This instruction has not been released for agent use."}</p>}<p className="mb-0 text-[11px] text-muted-foreground">A captured receipt is evidence of delivery. Inspect recorded behavior separately; no improvement is established by delivery alone.</p></div>}
  </div>;
}

function InstructionHistory({ graderId, onChanged }: { graderId: string; onChanged: () => Promise<void> }) {
  const loader = useCallback(() => wbInstructionReleases(graderId), [graderId]);
  const { data, error, reload } = useWorkbenchLoad(loader);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  async function restore(changeId: string | null) {
    setBusy(true); setActionError(null);
    try { await wbRollbackInstruction(graderId, changeId); await reload(); await onChanged(); }
    catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <details className="rounded-md border border-border p-3"><summary className="cursor-pointer text-[12px] font-medium">Instruction release history and rollback</summary><ErrorNotice error={error ?? actionError} /><p className="text-[12px] text-muted-foreground">Restoring a release or stopping delivery affects future eligible sessions. Already assigned sessions retain their recorded version.</p>{data?.length === 0 && <p className="text-[12px] text-muted-foreground">No released instructions in this scope.</p>}<div className="space-y-3">{data?.map((release) => <div key={release.id} className="space-y-2 border-t border-border pt-2"><div className="flex flex-wrap items-center gap-2 text-[12px]"><RecordBadge value={release.action} />{release.active && <RecordBadge value="active" />}<span className="text-muted-foreground">{relativeTime(release.created_at)}</span>{!release.active && release.change_id && <Button variant="outline" size="xs" disabled={busy} onClick={() => void restore(release.change_id)}>Restore this release</Button>}</div><JsonDetails title="Released instruction and scope" value={{ text: release.content, scope: release.scope }} /></div>)}</div>{data?.some((release) => release.active && release.change_id) && <Button variant="outline" size="sm" className="mt-3" disabled={busy} onClick={() => void restore(null)}>Stop instruction delivery for future runs</Button>}</details>;
}

function ChangeReport({ report, kind }: { report: WorkbenchChange["check_report"]; kind: WorkbenchChange["kind"] }) {
  if (!report) return <p className="text-[12px] text-muted-foreground">No check report yet. {kind === "grader" ? "Independent reviewed examples are required to measure grading quality." : "Instruction checks do not establish better behavior in future runs."}</p>;
  const message = typeof report.reason === "string" ? report.reason : typeof report.message === "string" ? report.message : null;
  const cases = Array.isArray(report.cases) ? report.cases as { assessment_id: string; trace_id: string; label: string; current_verdict?: string; candidate_verdict?: string; current_correct?: boolean; candidate_correct?: boolean }[] : [];
  return <div className="space-y-3"><div className="flex items-center gap-2"><h3 className="m-0 text-[12px] font-medium">Saved check report</h3><RecordBadge value={report.running === true ? "incomplete" : report.passed === true ? "passed" : "needs_review"} /></div>{message && <p className="text-[12px] text-muted-foreground">{message}</p>}
    {kind === "grader" && typeof report.total === "number" && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{[["Current correct", `${report.current_correct ?? 0} / ${report.total}`], ["Candidate correct", `${report.candidate_correct ?? 0} / ${report.total}`], ["Corrected errors", String(report.corrected ?? 0)], ["New errors", String(report.regressions ?? 0)]].map(([label, value]) => <div key={label} className="rounded-md bg-surface p-3"><span className="block text-[11px] text-muted-foreground">{label}</span><strong className="mt-1 block text-[16px] font-medium tabular-nums">{value}</strong></div>)}</div>}
    {cases.length > 0 && <div className="overflow-x-auto rounded-md border border-border"><table className="w-full text-left text-[12px]"><caption className="p-2 text-left text-[11px] text-muted-foreground">Same saved evidence and reviewed label for both grader versions.</caption><thead className="bg-surface"><tr><th className="p-2 font-medium">Source</th><th className="p-2 font-medium">Human label</th><th className="p-2 font-medium">Current</th><th className="p-2 font-medium">Candidate</th></tr></thead><tbody>{cases.map((item) => <tr key={item.assessment_id} className="border-t border-border"><td className="p-2"><Link className="underline" href={`/reward-models/traces/${item.trace_id}?assessment=${item.assessment_id}`}>Open trace</Link></td><td className="p-2"><RecordBadge value={item.label} /></td><td className="p-2">{item.current_verdict?.replaceAll("_", " ") ?? "Not completed"}{item.current_verdict ? item.current_correct ? " ✓" : " ✗" : ""}</td><td className="p-2">{item.candidate_verdict?.replaceAll("_", " ") ?? "Not completed"}{item.candidate_verdict ? item.candidate_correct ? " ✓" : " ✗" : ""}</td></tr>)}</tbody></table></div>}
    <JsonDetails title="Exact comparison inputs, outputs, and release gates" value={report} />
    {kind === "instruction" && <p className="text-[11px] text-muted-foreground">Passing these checks does not measure agent benefit. Later-run delivery and observed behavior remain separate.</p>}
  </div>;
}
