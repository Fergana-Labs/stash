"use client";

import { useEffect, useState } from "react";
import { Pin, Table2 } from "lucide-react";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditExample, imExamples, imGet, type Example } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";
import { LabelChip, labelSpace, type LabelSpace } from "../labels";

/** Recent examples as people read them, with their labels; pin the ones that must never break. */
export default function ExamplesCard() {
  const { modelId, version, refresh } = useWizard();
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [space, setSpace] = useState<LabelSpace | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!modelId) return;
    Promise.all([imGet(modelId), imExamples(modelId)]).then(([d, ex]) => { setSpace(labelSpace(d)); setExamples([...ex].reverse()); }).catch((e) => setError(errorMessage(e)));
  }, [modelId, version]);
  if (!modelId) return <CardShell icon={Table2} title="Examples"><NeedsModel /></CardShell>;
  async function togglePin(e: Example) {
    if (!modelId) return;
    try {
      const updated = await imEditExample(modelId, e.id, { pinned: !e.pinned });
      setExamples((xs) => xs?.map((x) => (x.id === e.id ? updated : x)) ?? xs);
      refresh();
    } catch (err) { setError(errorMessage(err)); }
  }
  return (
    <CardShell icon={Table2} title="Examples" subtitle={examples ? `${examples.length} total, ${examples.filter((e) => e.split === "eval").length} held out, newest first` : "Loading…"}>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
      <ul className="m-0 max-h-96 list-none space-y-1.5 overflow-y-auto p-0">
        {(examples ?? []).slice(0, 12).map((e) => (
          <li key={e.id} className="flex items-start gap-2.5 rounded-md border border-border px-2.5 py-2">
            <div className="max-h-24 min-w-0 flex-1 overflow-hidden"><ItemView item={e.item} /></div>
            <div className="flex shrink-0 items-center gap-1">
              {e.needs_review ? <span className="text-[11px] text-muted-foreground">{e.label ? "suggested " : "needs a label"}</span> : null}
              {e.label && <LabelChip label={e.label} kind={space?.kind} tone={e.needs_review ? "muted" : "you"} />}
              {e.label && !e.needs_review && <button type="button" aria-label={e.pinned ? "Unpin" : "Pin: must never get wrong"} aria-pressed={!!e.pinned} title={e.pinned ? "Pinned: a new version can't ship if it gets this wrong" : "Pin as must-never-get-wrong"} onClick={() => void togglePin(e)} className={cn("grid size-5 place-items-center rounded", e.pinned ? "text-brand-500" : "text-muted-foreground/40 hover:text-foreground")}><Pin className="size-3" /></button>}
            </div>
          </li>
        ))}
      </ul>
      {examples && examples.length > 12 && <p className="m-0 mt-1.5 text-[11.5px] text-muted-foreground">{examples.length - 12} more in the Golden set tab.</p>}
    </CardShell>
  );
}
