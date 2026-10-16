"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, Pin, Plus, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imAcceptSuggestions, imDeleteExample, imEditExample, imExamples, imGet, type Example, type Item } from "@/lib/intuition-api";
import { issuesOf, LabelChip, LabelPicker, labelSpace, PAIR_SPACE, type LabelSpace } from "@/components/wizard/labels";
import { useWizard } from "@/components/wizard/wizard-ui";
import UploaderCard from "@/components/wizard/cards/UploaderCard";
import GoldenCard from "@/components/wizard/cards/GoldenCard";
import { LabelerModal } from "@/components/wizard/cards/LabelerCard";
import AutosaveTextarea from "@/components/evals/AutosaveTextarea";
import { examplePreview, InlinePanel } from "@/components/evals/eval-ui";
import ItemView from "@/components/intuitions/ItemView";
import { Badge, FilterChips } from "./ItemRow";

type Filter = "all" | "todo" | "held" | "pinned" | `label:${string}`;
const SUGGESTED = /^Suggested [^:]+: ?/;

function Editor({ example, space, onChanged }: { example: Example; space: LabelSpace; onChanged: () => void }) {
  const { modelId } = useWizard();
  const suggested = example.needs_review ? example.label : null;
  const [value, setValue] = useState<string | null>(example.label);
  const [note] = useState(SUGGESTED.test(example.note) || example.note.startsWith("Generated") ? "" : example.note);
  const [error, setError] = useState("");
  const run = (fn: () => Promise<unknown>) => fn().then(onChanged).catch((e) => setError(errorMessage(e)));
  return (
    <div className="space-y-2.5">
      {suggested && <p className="m-0 flex items-start gap-1.5 text-[12px]"><Sparkles className="mt-0.5 size-3 text-brand-500" /><span>{example.note.replace(SUGGESTED, "Suggested: ")}</span></p>}
      <LabelPicker space={example.kind === "pair" ? PAIR_SPACE : space} value={value} suggested={suggested} commitLabel="Save"
        onPick={(label, go) => { setValue(label); if (go && modelId) void run(() => imEditExample(modelId, example.id, { label, needs_review: false })); }} />
      {modelId && <AutosaveTextarea value={note} label="Why this label?" placeholder="Explain what makes this good or bad…" save={(next) => imEditExample(modelId, example.id, { note: next })} onSaved={onChanged} />}
      <div className="flex flex-wrap items-center gap-2">
        {example.label && !example.needs_review && (
          <Button size="sm" variant={example.pinned ? "default" : "outline"} title="A pinned example is a regression test: no version can ship if it gets it wrong" onClick={() => modelId && void run(() => imEditExample(modelId, example.id, { pinned: !example.pinned }))}><Pin />{example.pinned ? "Pinned" : "Pin"}</Button>
        )}
        <Button size="sm" variant="ghost" aria-label="Delete example" onClick={() => modelId && void run(() => imDeleteExample(modelId, example.id))}><Trash2 /></Button>
      </div>
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
    </div>
  );
}

/** The golden set: every labeled example the intuition learns from and is measured on. */
export default function ExamplesPanel({ onTry }: { onTry?: (item: Item) => void }) {
  const { modelId, refresh, send, version } = useWizard();
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [space, setSpace] = useState<LabelSpace | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState<"" | "upload" | "label">("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!modelId) return;
    try {
      const [detail, ex] = await Promise.all([imGet(modelId), imExamples(modelId)]);
      setSpace(labelSpace(detail)); setExamples([...ex].reverse());
    } catch (e) { setError(errorMessage(e)); }
  }, [modelId]);
  useEffect(() => { void load(); }, [load, version]);

  const todo = (examples ?? []).filter((e) => e.needs_review);
  const suggestions = todo.filter((e) => e.label);
  const visible = useMemo(() => (examples ?? []).filter((e) => {
    if (filter === "todo") return e.needs_review;
    if (filter === "held") return e.split === "eval" && !e.needs_review;
    if (filter === "pinned") return e.pinned;
    if (filter.startsWith("label:")) {
      const id = filter.slice(6);
      return !e.needs_review && (space?.kind === "multi" ? (id === "none" ? e.label === "none" : issuesOf(e.label).includes(id)) : e.label === id);
    }
    return true;
  }), [examples, filter, space]);

  async function acceptAll() {
    if (!modelId) return;
    setBusy("Accepting…");
    try {
      const { accepted } = await imAcceptSuggestions(modelId);
      await load(); refresh();
      send(`Accepted ${accepted} suggested labels without changes.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

  const labeled = (examples ?? []).filter((e) => !e.needs_review);
  const options = [
    { id: "all" as Filter, label: "All", count: examples?.length },
    ...(todo.length ? [{ id: "todo" as Filter, label: "Needs a label", count: todo.length }] : []),
    ...(space?.options ?? []).map((o) => ({ id: `label:${o.id}` as Filter, label: o.id, count: labeled.filter((e) => (space?.kind === "multi" ? issuesOf(e.label).includes(o.id) : e.label === o.id)).length })),
    ...(space?.kind === "multi" ? [{ id: "label:none" as Filter, label: "No issues", count: labeled.filter((e) => e.label === "none").length }] : []),
    { id: "held" as Filter, label: "Held out", count: labeled.filter((e) => e.split === "eval").length, title: "Never trained on: used to measure accuracy honestly" },
    { id: "pinned" as Filter, label: "Pinned", count: labeled.filter((e) => e.pinned).length, title: "Must never get wrong: a version that misses one can't ship" },
  ];

  return (
    <div className="flex flex-col gap-3 [&>section]:my-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="m-0 max-w-xl text-[12.5px] text-muted-foreground">Your labeled examples: what the intuition learns from, and (held out) what it is measured on. Real, hard cases teach the most.</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={adding === "upload" ? "secondary" : "outline"} onClick={() => setAdding(adding === "upload" ? "" : "upload")}><Plus />Add real examples</Button>
          {todo.length > 0 && <Button size="sm" onClick={() => setAdding("label")}>Label {todo.length}</Button>}
          {suggestions.length > 0 && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void acceptAll()} title="Confirm every pending suggestion as is">Accept all {suggestions.length} suggestions</Button>}
        </div>
      </div>

      {adding === "upload" && <UploaderCard prompt="Add real examples, especially hard and borderline ones." />}
      <LabelerModal open={adding === "label"} onOpenChange={(o) => { setAdding(o ? "label" : ""); if (!o) void load(); }} />
      {(examples?.length ?? 0) >= 4 && (
        <details className="rounded-lg border border-border [&>summary]:px-3.5 [&>summary]:py-2 [&[open]>summary]:border-b [&[open]>summary]:border-border">
          <summary className="cursor-pointer text-[12.5px]">Health check <span className="text-muted-foreground">— coverage per label, near-duplicates, look-alikes labeled differently</span></summary>
          <div className="p-2 [&>section]:my-0 [&>section]:border-0 [&>section]:shadow-none"><GoldenCard /></div>
        </details>
      )}
      <FilterChips value={filter} onChange={setFilter} options={options} />
      {error && <p role="alert" className="m-0 text-[11.5px] text-destructive">{error}</p>}
      {examples === null && <p role="status" className="m-0 text-[12px] text-muted-foreground">Loading…</p>}
      {examples && visible.length === 0 && <p className="m-0 rounded-lg border border-dashed border-border p-6 text-center text-[12.5px] text-muted-foreground">{examples.length ? "Nothing matches this filter." : "No examples yet. Add real ones, or generate a few to label."}</p>}
      {visible.length > 0 && <div className="overflow-x-auto rounded border border-border">
        <table className="w-full text-left text-xs" aria-label="Golden set examples">
          <thead className="bg-surface/50 text-[11px] text-muted-foreground"><tr className="border-b border-border">
            <th scope="col" className="w-10 px-3 py-2 font-medium">#</th>
            <th scope="col" className="px-3 py-2 font-medium">Example</th>
            <th scope="col" className="px-3 py-2 font-medium">Label</th>
            <th scope="col" className="px-3 py-2 font-medium">Source</th>
            <th scope="col" className="px-3 py-2 font-medium">Split</th>
            {onTry && <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Actions</span></th>}
          </tr></thead>
          <tbody>{visible.slice(0, 200).map((e, index) => <Fragment key={e.id}>
            <tr className="border-b border-border last:border-0 hover:bg-surface/40">
              <td className="px-3 py-2 align-top tabular-nums text-muted-foreground">{index + 1}</td>
              <td className="w-full min-w-48 max-w-xl px-3 py-2 align-top">
                <button type="button" className="flex w-full items-start gap-2 text-left" aria-label={`Inspect example ${index + 1}`} aria-expanded={open === e.id} aria-controls={`example-${e.id}`} onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <ChevronDown className={`mt-0.5 size-3 shrink-0 transition-transform ${open === e.id ? "rotate-180" : ""}`} />
                  <span className="line-clamp-2 leading-5">{e.item_b ? `A: ${examplePreview(e.item)} · B: ${examplePreview(e.item_b)}` : examplePreview(e.item)}</span>
                </button>
                {e.pinned && <span className="ml-5"><Badge tone="brand">pinned</Badge></span>}
              </td>
              <td className="px-3 py-2 align-top">{e.needs_review
                ? (e.label ? <><LabelChip label={e.label} kind={space?.kind} tone="muted" /><span className="block text-[10.5px] text-brand-600 dark:text-brand-400">suggested</span></> : <Badge tone="warn">needs a label</Badge>)
                : <LabelChip label={e.label} kind={space?.kind} tone="you" />}</td>
              <td className="px-3 py-2 align-top whitespace-nowrap text-muted-foreground">{e.note.startsWith("Adversarial repair") ? "repair" : e.source === "production" ? "from inbox" : e.source === "generated" ? "generated" : "real"}</td>
              <td className="px-3 py-2 align-top whitespace-nowrap text-muted-foreground">{e.split === "eval" ? "Held out" : "Train"}</td>
              {onTry && <td className="px-3 py-2 align-top"><Button size="xs" variant="ghost" onClick={() => onTry(e.item)}>Open in sandbox</Button></td>}
            </tr>
            {open === e.id && <tr id={`example-${e.id}`}><td colSpan={onTry ? 6 : 5} className="border-b border-border p-0">
              <InlinePanel title={`Example ${index + 1}`} onClose={() => setOpen(null)} className="rounded-none border-0">
                <div className={e.item_b ? "grid gap-3 sm:grid-cols-2" : ""}>
                  <div className="rounded border border-border bg-background p-3">{e.item_b && <p className="mb-2 text-xs font-medium">A</p>}<ItemView item={e.item} clamp={false} /></div>
                  {e.item_b && <div className="rounded border border-border bg-background p-3"><p className="mb-2 text-xs font-medium">B</p><ItemView item={e.item_b} clamp={false} /></div>}
                </div>
                {space && <Editor example={e} space={space} onChanged={() => { void load(); refresh(); }} />}
                {onTry && <div className="flex flex-wrap justify-end gap-2"><Button size="sm" variant="outline" onClick={() => onTry(e.item)}>Open {e.item_b ? "A in sandbox" : "in sandbox"}</Button>{e.item_b && <Button size="sm" variant="outline" onClick={() => onTry(e.item_b!)}>Open B in sandbox</Button>}</div>}
              </InlinePanel>
            </td></tr>}
          </Fragment>)}</tbody>
        </table>
      </div>}
    </div>
  );
}
