"use client";

import { Fragment, useEffect, useState } from "react";
import { Pin, Table2 } from "lucide-react";
import { examplePreview } from "@/components/evals/eval-ui";
import ItemView from "@/components/intuitions/ItemView";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditExample, imExamples, imGet, type Example } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";
import { CardShell, NeedsModel, useWizard } from "../wizard-ui";

/** Every example with its label, split and source; open one to read it or fix its label, pin the ones that must never break. */
export default function ExamplesCard() {
  const { modelId, version, refresh } = useWizard();
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [labels, setLabels] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (modelId) imExamples(modelId).then(setExamples).catch((e) => setError(errorMessage(e))); }, [modelId, version]);
  useEffect(() => {
    if (!modelId) return;
    imGet(modelId).then((d) => setLabels(d.model.output_type === "choice" ? ((d.draft ?? d.active)?.labels ?? []).map((l) => l.id) : ["good", "bad"])).catch(() => undefined);
  }, [modelId]);
  if (!modelId) return <CardShell icon={Table2} title="Examples"><NeedsModel /></CardShell>;
  async function edit(e: Example, body: Parameters<typeof imEditExample>[2]) {
    if (!modelId) return;
    try {
      const updated = await imEditExample(modelId, e.id, body);
      setExamples((xs) => xs?.map((x) => (x.id === e.id ? updated : x)) ?? xs);
      refresh();
    } catch (err) { setError(errorMessage(err)); }
  }
  return (
    <CardShell icon={Table2} title="Examples" subtitle={examples ? `${examples.length} total · ${examples.filter((e) => e.split === "eval").length} held out` : "Loading…"}>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
      <div className="max-h-72 overflow-auto rounded border border-border">
        <table className="w-full text-left text-[12px]">
          <thead className="sticky top-0 bg-surface text-muted-foreground"><tr className="[&>th]:px-2.5 [&>th]:py-1.5 [&>th]:font-medium"><th>Example</th><th>Label</th><th>Split</th><th>Source</th><th><span className="sr-only">Pinned</span></th></tr></thead>
          <tbody>
            {(examples ?? []).map((e) => (
              <Fragment key={e.id}>
              <tr className={cn("border-t border-border [&>td]:px-2.5 [&>td]:py-1.5", open === e.id && "bg-muted/40")}>
                <td className="max-w-[22rem] truncate"><button type="button" aria-expanded={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)} className="max-w-full truncate text-left hover:underline">{typeof e.item === "object" && e.item.kind === "image" ? `🖼 ${String(e.item.name ?? "image")}` : examplePreview(e.item)}</button></td>
                <td>{e.needs_review ? <span className="text-muted-foreground">{e.label ? `${e.label}?` : "—"}</span> : e.label}</td>
                <td className="text-muted-foreground">{e.split === "eval" ? "held out" : "train"}</td>
                <td className="text-muted-foreground">{e.note.startsWith("Adversarial repair") ? "repair" : e.source}</td>
                <td>{e.label && !e.needs_review && <button type="button" aria-label={e.pinned ? "Unpin" : "Pin: must never get wrong"} aria-pressed={!!e.pinned} title={e.pinned ? "Pinned: a new version can't ship if it gets this wrong" : "Pin as must-never-get-wrong"} onClick={() => void edit(e, { pinned: !e.pinned })} className={cn("grid size-5 place-items-center rounded", e.pinned ? "text-brand-500" : "text-muted-foreground/40 hover:text-foreground")}><Pin className="size-3" /></button>}</td>
              </tr>
              {open === e.id && <tr className="bg-muted/40"><td colSpan={5} className="px-2.5 pb-2.5">
                <ItemView item={e.item} />
                {e.note && <p className="m-0 mt-1.5 text-[11.5px] text-muted-foreground">Note: {e.note}</p>}
                {labels.length > 0 && <label className="mt-2 flex items-center gap-2 text-[11.5px] text-muted-foreground">Label
                  <select aria-label="Label" value={e.needs_review ? "" : e.label ?? ""} onChange={(ev) => void edit(e, ev.target.value ? { label: ev.target.value, needs_review: false } : { needs_review: true })} className="h-7 rounded border border-border bg-background px-1.5 text-[12px] text-foreground">
                    <option value="">— needs review —</option>
                    {labels.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </label>}
              </td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </CardShell>
  );
}
