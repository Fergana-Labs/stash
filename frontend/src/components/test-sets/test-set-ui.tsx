"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/select";
import { evalInputClass } from "@/components/evals/eval-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { setHref, tsCaseFromTrace, tsCreate, tsList, type TestSetSummary } from "@/lib/test-sets-api";
import type { RmStep } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Evals | Test sets, on top of both lists. */
export function EvalsViewToggle({ view }: { view: "evals" | "test-sets" }) {
  const item = (value: typeof view, href: string, label: string) => <Link href={href} aria-current={view === value ? "page" : undefined}
    className={cn("rounded px-2.5 py-1", view === value ? "bg-surface font-medium text-foreground shadow-[inset_0_0_0_1px_var(--border-color)]" : "text-muted-foreground hover:text-foreground")}>{label}</Link>;
  return <nav aria-label="Evals or test sets" className="mb-4 flex gap-1 text-xs">
    {item("evals", "/reward-models/evals", "Evals")}
    {item("test-sets", "/reward-models/evals/test-sets", "Test sets")}
  </nav>;
}

export function GateBadge({ gate }: { gate: "pass" | "fail" }) {
  return <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium", gate === "pass" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive")}>
    {gate === "pass" ? "Pass" : "Fail"}
  </span>;
}

/** User and assistant messages the way the backend cuts a trace into a case. */
export function conversationTurns(steps: RmStep[]) {
  return steps.filter((s) => (s.role === "user" || s.role === "assistant") && !s.tool_name && s.content.trim());
}

const selectClass = "h-8 w-full min-w-0 px-2 text-xs";

const NEW = "__new";

/**
 * Turn a trace into a test case. From the trace page you pick which user turn
 * to start from; from a behavior hit the turn is fixed by the hit.
 */
export function AddToTestSetDialog({ open, onOpenChange, traceId, steps, uptoIdx, title }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  traceId: string;
  /** The trace's steps, to choose the user turn and prefill the agent's answer. */
  steps?: RmStep[];
  /** A fixed turn (a behavior hit's end): the case ends at the user message at or before it. */
  uptoIdx?: number;
  title?: string;
}) {
  const router = useRouter();
  const [sets, setSets] = useState<TestSetSummary[] | null>(null);
  const [setId, setSetId] = useState("");
  const [newName, setNewName] = useState("");
  const [turnIdx, setTurnIdx] = useState("");
  const [expected, setExpected] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const turns = useMemo(() => conversationTurns(steps ?? []), [steps]);
  const userTurns = turns.filter((t) => t.role === "user");
  const answerAfter = (idx: number) => turns.find((t) => t.index > idx && t.role === "assistant")?.content ?? "";

  useEffect(() => {
    if (!open) return;
    setError("");
    setExpected(steps && userTurns[0] ? answerAfter(userTurns[0].index) : "");
    setTurnIdx(userTurns[0] ? String(userTurns[0].index) : "");
    tsList().then((r) => { setSets(r.test_sets); setSetId((cur) => cur || r.test_sets[0]?.id || NEW); })
      .catch((e) => setError(errorMessage(e)));
    // Reset each time it opens; the trace's turns don't change while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function save() {
    setSaving(true); setError("");
    try {
      const target = setId === NEW ? await tsCreate({ name: newName.trim() }) : sets!.find((s) => s.id === setId)!;
      const upto = steps ? (turnIdx ? Number(turnIdx) : undefined) : uptoIdx;
      await tsCaseFromTrace(target.id, { trace_id: traceId, upto_idx: upto, expected: expected.trim() });
      toast.success(`Added to ${target.name}`, { action: { label: "Open", onClick: () => router.push(setHref(target.id)) } });
      onOpenChange(false);
      if (setId === NEW) { setSets(null); setSetId(target.id); setNewName(""); }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const ready = !!setId && (setId !== NEW || !!newName.trim()) && (!steps || !!turnIdx);
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-lg [&>*]:min-w-0">
    <DialogHeader>
      <DialogTitle>Add to test set</DialogTitle>
      <DialogDescription>{steps ? "The conversation up to the message you pick becomes a case." : "The conversation up to the user message behind this hit becomes a case."}{title && <span className="mt-0.5 block truncate">From “{title}”</span>}</DialogDescription>
    </DialogHeader>
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {!sets && !error ? <p role="status" className="text-xs text-muted-foreground">Loading test sets…</p> : <div className="grid min-w-0 gap-3 text-xs [&>label]:min-w-0">
      <label className="grid gap-1"><span className="font-medium">Test set</span>
        <Select aria-label="Test set" className={selectClass} value={setId} onChange={setSetId} options={[...(sets ?? []).map((s) => ({ value: s.id, label: s.name })), { value: NEW, label: "New test set…" }]} />
      </label>
      {setId === NEW && <label className="grid gap-1"><span className="font-medium">Name</span>
        <input autoFocus className={evalInputClass} value={newName} maxLength={120} onChange={(e) => setNewName(e.target.value)} placeholder="Support regressions" /></label>}
      {steps && <label className="grid gap-1"><span className="font-medium">Start from</span>
        {userTurns.length
          ? <Select aria-label="Start from" className={selectClass} value={turnIdx} onChange={(v) => { setTurnIdx(v); setExpected(answerAfter(Number(v))); }}
            options={userTurns.map((t, i) => ({ value: String(t.index), label: `Message ${i + 1}: ${t.content.replace(/\s+/g, " ").slice(0, 70)}` }))} />
          : <span className="text-muted-foreground">This trace has no user message to start from.</span>}
      </label>}
      <div className="grid gap-1"><label className="grid gap-1"><span className="font-medium">What should the agent answer?</span>
        <textarea className={evalInputClass} rows={5} value={expected} maxLength={20_000} onChange={(e) => setExpected(e.target.value)}
          placeholder={steps ? "The answer that counts as right" : "What it should have said"} /></label>
        <span className="text-[11px] text-muted-foreground">Runs pass when the answer says the same thing. Leave empty to rely only on the set’s evals.</span>
      </div>
    </div>}
    <DialogFooter>
      <Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
      <Button size="sm" disabled={!ready || saving} onClick={() => void save()}>{saving ? "Adding…" : "Add case"}</Button>
    </DialogFooter>
  </DialogContent></Dialog>;
}

/** Header action on the trace page. */
export function AddToTestSetButton({ traceId, steps, title }: { traceId: string; steps: RmStep[]; title?: string }) {
  const [open, setOpen] = useState(false);
  return <>
    <Button size="xs" variant="outline" onClick={() => setOpen(true)}>Add to test set</Button>
    <AddToTestSetDialog open={open} onOpenChange={setOpen} traceId={traceId} steps={steps} title={title} />
  </>;
}
