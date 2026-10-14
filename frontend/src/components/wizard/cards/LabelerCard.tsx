"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, Pin, Sparkles, Tags } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditExample, imExamples, imGet, type Example } from "@/lib/intuition-api";
import { wzReport } from "@/lib/wizard-api";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";
import { LabelPicker, labelSpace, showLabel, type LabelSpace } from "../labels";

type Which = "needs_review" | "all" | "mistakes";
const SUGGESTED = /^Suggested [^:]+: ?([\s\S]*)$/;

/**
 * One item at a time: pick a label (number keys work), optionally say why, and
 * pin it if it must never be gotten wrong. Generated items arrive with a
 * suggested label and the reason for it; accept or change it.
 */
export function Labeler({ which = "needs_review", onDone }: { which?: Which; onDone?: () => void }) {
  const { modelId, send, refresh } = useWizard();
  const [queue, setQueue] = useState<Example[] | null>(null);
  const [space, setSpace] = useState<LabelSpace | null>(null);
  const [pairSpace, setPairSpace] = useState<LabelSpace | null>(null);
  const [index, setIndex] = useState(0);
  const [done, setDone] = useState<Record<string, string>>({});
  const [value, setValue] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [pin, setPin] = useState(false);
  const [error, setError] = useState("");
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    if (!modelId) return;
    (async () => {
      try {
        const [detail, examples] = await Promise.all([imGet(modelId), imExamples(modelId)]);
        setSpace(labelSpace(detail)); setPairSpace(labelSpace(detail, true));
        let picked = examples;
        if (which === "needs_review") picked = examples.filter((e) => e.needs_review);
        if (which === "mistakes") {
          const report = (await wzReport(modelId)).report;
          const wrong = new Set((report?.holdout.rows ?? []).filter((r) => r.predicted !== r.label).map((r) => r.example_id));
          picked = examples.filter((e) => wrong.has(e.id));
        }
        setQueue(picked);
      } catch (e) { setError(errorMessage(e)); }
    })();
  }, [modelId, which]);

  const current = queue?.[index];
  const suggestion = useMemo(
    () => (current?.needs_review && current.label ? { label: current.label, reason: SUGGESTED.exec(current.note)?.[1] ?? "" } : null),
    [current],
  );
  useEffect(() => {
    setValue(current?.label ?? null);
    setNote(current && !current.needs_review ? current.note : "");
    setPin(!!current?.pinned);
  }, [current]);

  const finish = useCallback((labeled: Record<string, string>) => {
    if (finished) return;
    setFinished(true);
    refresh();
    const counts = Object.values(labeled).reduce<Record<string, number>>((acc, l) => ({ ...acc, [l]: (acc[l] ?? 0) + 1 }), {});
    const summary = Object.entries(counts).map(([l, n]) => `${n} ${showLabel(l)}`).join(", ");
    send(Object.keys(labeled).length ? `Labeled ${Object.keys(labeled).length} example${Object.keys(labeled).length === 1 ? "" : "s"}: ${summary}.` : "Closed the labeler without labeling.", "event");
    onDone?.();
  }, [finished, refresh, send, onDone]);

  const commit = useCallback(async (label: string) => {
    if (!modelId || !current || !queue) return;
    setError("");
    try {
      const body: Parameters<typeof imEditExample>[2] = { label, needs_review: false };
      if (note.trim() && note.trim() !== current.note) body.note = note.trim();
      else if (suggestion) body.note = ""; // the suggestion's reason was Claude's, not the person's
      if (pin !== !!current.pinned) body.pinned = pin;
      await imEditExample(modelId, current.id, body);
      const next = { ...done, [current.id]: label };
      setDone(next);
      if (index + 1 >= queue.length) finish(next); else setIndex(index + 1);
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId, current, queue, done, index, finish, note, pin, suggestion]);

  if (!modelId) return <NeedsModel />;
  const total = queue?.length ?? 0;
  const labeledCount = Object.keys(done).length;
  const options = current?.kind === "pair" ? pairSpace : space;
  const keysHint = options?.kind === "multi" ? `1–${options.options.length} toggle · 0 none · ↵ save` : `press 1–${options?.options.length ?? 0}`;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 text-[12px] text-muted-foreground">
        <span>{queue ? (finished ? `Done — ${labeledCount} labeled` : total ? `${Math.min(index + 1, total)} of ${total} · ${keysHint}` : "") : "Loading…"}</span>
        {!finished && queue && total > 0 && <Button size="xs" variant="ghost" onClick={() => finish(done)}>{labeledCount ? "Done for now" : "Not now"}</Button>}
      </div>
      {error && <p role="alert" className="m-0 mb-2 text-[11.5px] text-destructive">{error}</p>}
      {queue && total === 0 && <p className="m-0 text-[12px] text-muted-foreground">{which === "mistakes" ? "No held-out mistakes to review." : "Nothing needs a label right now."}</p>}
      {queue && total > 0 && !finished && current && options && (
        <div className="space-y-3">
          <div className="h-1 overflow-hidden rounded-full bg-raised"><div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${(labeledCount / total) * 100}%` }} /></div>
          <div className="max-h-[45vh] overflow-y-auto rounded-md border border-border bg-surface/30 p-3">
            {current.kind === "pair" && current.item_b ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">A</div><ItemView item={current.item} clamp={false} /></div>
                <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">B</div><ItemView item={current.item_b} clamp={false} /></div>
              </div>
            ) : <ItemView item={current.item} clamp={false} />}
          </div>
          {suggestion && (
            <p className="m-0 flex items-start gap-1.5 rounded-md bg-brand-500/8 px-2.5 py-1.5 text-[12px]">
              <Sparkles className="mt-0.5 size-3 shrink-0 text-brand-500" />
              <span>Suggested <b>{showLabel(suggestion.label, options.kind)}</b>{suggestion.reason && <span className="text-muted-foreground"> — {suggestion.reason}</span>}. Accept it or pick another.</span>
            </p>
          )}
          <LabelPicker space={options} value={value} suggested={suggestion?.label} onPick={(label, go) => { setValue(label); if (go) void commit(label); }} />
          <div className="flex flex-wrap items-center gap-2">
            <input aria-label="Why (optional)" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why? (optional — reasons teach the model more than labels)" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground/40" />
            <label className="flex items-center gap-1 text-[11.5px] text-muted-foreground" title="A pinned example is a regression test: no version can ship if it gets it wrong"><input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} /><Pin className="size-3" />Must get right</label>
            <Button size="sm" variant="ghost" disabled={index === 0} aria-label="Previous" onClick={() => setIndex(index - 1)}><ChevronLeft /></Button>
            <Button size="sm" variant="ghost" onClick={() => (index + 1 >= total ? finish(done) : setIndex(index + 1))}>Skip</Button>
          </div>
        </div>
      )}
      {finished && <p className="m-0 text-[12px] text-muted-foreground">Thanks — your labels are saved.</p>}
    </div>
  );
}


/** Labeling is its own focused step: a modal, so it is clear what is being asked. */
export function LabelerModal({ open, onOpenChange, which = "needs_review" }: { open: boolean; onOpenChange: (open: boolean) => void; which?: Which }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{which === "mistakes" ? "Check the examples it got wrong" : "Label examples"}</DialogTitle>
          <DialogDescription>Pick the right answer for each one, the way you would on the job. Add a reason when it is a close call: reasons teach it more than labels. Suggested labels are only guesses until you accept them.</DialogDescription>
        </DialogHeader>
        {open && <Labeler which={which} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

/** In the chat: what is waiting to be labeled, and a button into the labeling modal (opened right away when the wizard asks). */
export default function LabelerCard({ which = "needs_review", fresh = false }: { which?: Which; fresh?: boolean }) {
  const { modelId, version } = useWizard();
  const [open, setOpen] = useState(fresh);
  const [waiting, setWaiting] = useState<number | null>(null);
  useEffect(() => {
    if (!modelId) return;
    imExamples(modelId).then((ex) => setWaiting(ex.filter((e) => e.needs_review).length)).catch(() => setWaiting(null));
  }, [modelId, version, open]);
  if (!modelId) return <CardShell icon={Tags} title="Label examples"><NeedsModel /></CardShell>;
  return (
    <CardShell icon={Tags} title="Label examples" subtitle={which === "mistakes" ? "Held-out examples it got wrong" : waiting == null ? "Loading…" : waiting ? `${waiting} waiting for your label` : "Nothing waiting"}>
      <Button size="sm" disabled={which === "needs_review" && waiting === 0} onClick={() => setOpen(true)}>{which === "mistakes" ? "Review mistakes" : waiting ? `Label ${waiting}` : "All labeled"}</Button>
      <LabelerModal open={open} onOpenChange={setOpen} which={which} />
    </CardShell>
  );
}
