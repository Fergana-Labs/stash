"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wbAddReviewer, wbRemoveReviewer, wbTraceReviewers } from "@/lib/workbench-api";
import { ErrorNotice, inputClass, useWorkbenchLoad } from "./workbench-ui";

export default function TraceReviewAccess({ traceId, viewerId }: { traceId: string; viewerId: string }) {
  const [open, setOpen] = useState(false);
  return <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="mt-2 text-[12px]"><summary className="cursor-pointer text-muted-foreground">Team review access</summary>{open && <ReviewAccessEditor traceId={traceId} viewerId={viewerId} />}</details>;
}

function ReviewAccessEditor({ traceId, viewerId }: { traceId: string; viewerId: string }) {
  const loader = useCallback(() => wbTraceReviewers(traceId), [traceId]);
  const { data, loading, error, reload } = useWorkbenchLoad(loader);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const owner = data?.owner_user_id === viewerId;
  async function grant(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setActionError(null);
    try { await wbAddReviewer(traceId, email.trim()); setEmail(""); await reload(); }
    catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function remove(userId: string) {
    setBusy(true); setActionError(null);
    try { await wbRemoveReviewer(traceId, userId); await reload(); }
    catch (e) { setActionError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <div className="mt-2 space-y-3 rounded-lg border border-border p-3"><ErrorNotice error={error ?? actionError} onRetry={() => void reload()} />{loading && <p>Loading access…</p>}{data && <><p className="m-0 text-muted-foreground">Reviewers can inspect this trace and its assessments, and submit feedback. Grader and instruction releases remain with the owner. Sharing review access does not authorize training on the trace.</p><div className="space-y-2">{data.reviewers.map((reviewer) => <div key={reviewer.user_id} className="flex items-center justify-between gap-2"><span>{reviewer.display_name || reviewer.email}</span>{owner && <Button size="xs" variant="ghost" disabled={busy} onClick={() => void remove(reviewer.user_id)}>Remove {reviewer.display_name || reviewer.email}</Button>}</div>)}{data.reviewers.length === 0 && <p className="m-0 text-muted-foreground">No additional reviewers.</p>}</div>{owner && <form onSubmit={(event) => void grant(event)} className="flex items-end gap-2"><div className="min-w-0 flex-1"><Field label="Reviewer’s Stash account email"><input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} /></Field></div><Button type="submit" size="sm" disabled={busy || !email.trim()}>{busy ? "Saving…" : "Grant access"}</Button></form>}</>}</div>;
}
