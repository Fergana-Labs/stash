"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditDraft, type ModelDetail } from "@/lib/intuition-api";
import { wzFromCorrections, type Discovery } from "@/lib/wizard-api";
import BriefCard from "@/components/wizard/cards/BriefCard";
import CriteriaCard from "@/components/wizard/cards/CriteriaCard";

/** Must match spec.BRIEF_MARKER on the server: everything after it is generated from the brief. */
export const BRIEF_MARKER = "\n\n— From the eval brief —\n";

/** The instructions Jev reads: yours (editable) plus the brief, compiled in automatically. */
function Instructions({ detail, onSaved }: { detail: ModelDetail; onSaved: () => void }) {
  const full = (detail.draft ?? detail.active)?.description ?? "";
  const [own, fromBrief = ""] = full.split(BRIEF_MARKER);
  const [text, setText] = useState(own);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setText(own), [own]);
  async function save() {
    setBusy(true); setError("");
    try { await imEditDraft(detail.model.id, { description: text }); onSaved(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return (
    <section aria-label="Instructions" className="rounded-lg border border-border p-3.5">
      <div className="mb-1.5 flex items-center justify-between gap-2"><h3 className="m-0 text-[13px] font-semibold">What the judge reads</h3>{text !== own && <Button size="xs" disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Save"}</Button>}</div>
      <textarea aria-label="Your instructions" rows={4} maxLength={5000} value={text} onChange={(e) => setText(e.target.value)} className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-2 text-[12.5px] leading-5 outline-none focus:border-foreground/40" />
      {fromBrief ? (
        <details className="mt-2">
          <summary className="cursor-pointer text-[11.5px] text-muted-foreground">+ Added from the brief (updates when the brief changes)</summary>
          <pre className="m-0 mt-1.5 rounded-md bg-surface/60 px-2.5 py-2 font-sans text-[12px] leading-5 whitespace-pre-wrap text-muted-foreground">{fromBrief}</pre>
        </details>
      ) : <p className="m-0 mt-1 text-[11px] text-muted-foreground">Fill in the brief and it is added here automatically.</p>}
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
    </section>
  );
}

/** Setup: the brief, the instructions the judge reads, and the criteria it answers. */
export default function SetupPanel({ detail, onSaved }: { detail: ModelDetail; onSaved: () => void }) {
  const [proposals, setProposals] = useState<{ key: number; items: Discovery["insights"] } | null>(null);
  const [error, setError] = useState("");
  async function fromCorrections() {
    setError("");
    try { const found = await wzFromCorrections(detail.model.id); setProposals({ key: Date.now(), items: found.insights }); }
    catch (e) { setError(errorMessage(e)); }
  }
  return (
    <div className="flex flex-col gap-4 [&>section]:my-0">
      <BriefCard />
      <Instructions detail={detail} onSaved={onSaved} />
      <CriteriaCard key={proposals?.key ?? "criteria"} proposals={proposals?.items.map((i) => ({ ...i.question, insight: i.insight }))} />
      <div className="flex flex-wrap items-start gap-3 rounded-lg bg-surface/50 px-3.5 py-2.5 text-[12px] text-muted-foreground">
        <p className="m-0 flex-1 min-w-60"><b className="text-foreground">How criteria work.</b> Jev answers each criterion about every input with a probability (&ldquo;82% yes, it promises a refund&rdquo;). Jev also answers the task itself directly. A small model trained on your labels learns how much each answer should count, so criteria that predict your labels gain weight and unhelpful ones fade. Good criteria are things you can see in the input, one property each.</p>
        <Button size="xs" variant="outline" onClick={() => void fromCorrections()} title="Turn the reasons you gave when correcting it into criteria">Suggest from my corrections</Button>
      </div>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}
