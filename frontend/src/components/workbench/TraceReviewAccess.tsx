"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wbAddReviewer, wbRemoveReviewer, wbTraceReviewers, wbReviewerSuggestions, type TraceReviewers } from "@/lib/workbench-api";
import { ErrorNotice, inputClass, useWorkbenchLoad } from "./workbench-ui";

export default function TraceReviewAccess({ traceId, viewerId }: { traceId: string; viewerId: string }) {
  const [open, setOpen] = useState(false);
  const actions = useRef<HTMLButtonElement>(null);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button ref={actions} variant="ghost" size="icon-sm" aria-label="Trace actions" title="Trace actions">
            <MoreHorizontal className="size-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" onCloseAutoFocus={(event) => { if (open) event.preventDefault(); }}>
          <DropdownMenuItem onSelect={() => setOpen(true)}>Share</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DialogContent onCloseAutoFocus={(event) => { event.preventDefault(); actions.current?.focus(); }}>
        <DialogTitle>Share trace</DialogTitle>
        <DialogDescription>Invite teammates to read this trace and leave comments.</DialogDescription>
        {open && <ReviewAccessEditor traceId={traceId} viewerId={viewerId} />}
      </DialogContent>
    </Dialog>
  );
}

function ReviewAccessEditor({ traceId, viewerId }: { traceId: string; viewerId: string }) {
  const loader = useCallback(() => wbTraceReviewers(traceId), [traceId]);
  const { data, loading, error, reload } = useWorkbenchLoad(loader);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const owner = data?.owner_user_id === viewerId;
  const [suggestions, setSuggestions] = useState<TraceReviewers["reviewers"]>([]);
  const [active, setActive] = useState(0);
  const [selectedEmail, setSelectedEmail] = useState("");
  const listId = useId();
  useEffect(() => {
    if (!owner || email.trim().length < 2 || email === selectedEmail) return;
    let cancelled = false;
    const timer = setTimeout(() => { void wbReviewerSuggestions(traceId, email).then((items) => {
      if (!cancelled) setSuggestions(items);
    }).catch(() => { if (!cancelled) setSuggestions([]); }); }, 200);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [email, owner, selectedEmail, traceId]);
  function choose(value: string) { setEmail(value); setSelectedEmail(value); setSuggestions([]); }

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
  return <div className="space-y-3"><ErrorNotice error={error ?? actionError} onRetry={() => void reload()} />{loading && <p>Loading access…</p>}{data && <><div className="space-y-2">{data.reviewers.map((reviewer) => <div key={reviewer.user_id} className="flex items-center justify-between gap-2"><span>{reviewer.display_name || reviewer.email}</span>{owner && <Button size="xs" variant="ghost" disabled={busy} onClick={() => void remove(reviewer.user_id)}>Remove {reviewer.display_name || reviewer.email}</Button>}</div>)}{data.reviewers.length === 0 && <p className="m-0 text-muted-foreground">No additional reviewers.</p>}</div>{owner && <form onSubmit={(event) => void grant(event)} className="flex items-end gap-2"><div className="min-w-0 flex-1"><Field label="Name or email"><div className="relative"><input required role="combobox" aria-autocomplete="list" aria-controls={listId} aria-expanded={suggestions.length > 0} aria-activedescendant={suggestions[active] ? `${listId}-${active}` : undefined} autoComplete="off" value={email} onChange={(e) => { setEmail(e.target.value); setSuggestions([]); setActive(0); }} onKeyDown={(e) => {
      if (e.key === "Escape") { setSuggestions([]); e.stopPropagation(); }
      if (!suggestions.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive((n) => (n + 1) % suggestions.length); }
      if (e.key === "ArrowUp") { e.preventDefault(); setActive((n) => (n + suggestions.length - 1) % suggestions.length); }
      if (e.key === "Enter") { e.preventDefault(); choose(suggestions[active].email); }
    }} className={inputClass} />{suggestions.length > 0 && <ul id={listId} role="listbox" className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover p-1 shadow-lg">{suggestions.map((person, index) => <li key={person.user_id} id={`${listId}-${index}`} role="option" aria-selected={active === index} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(person.email)} className={`cursor-pointer rounded p-2 text-xs ${active === index ? "bg-accent" : "hover:bg-accent"}`}><div>{person.display_name || person.email}</div><div className="text-muted-foreground">{person.email}</div></li>)}</ul>}</div></Field></div><Button type="submit" size="sm" disabled={busy || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())}>{busy ? "Saving…" : "Grant access"}</Button></form>}</>}</div>;
}
