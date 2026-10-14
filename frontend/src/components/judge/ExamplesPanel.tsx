"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Pin, Plus, Sparkles, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imAcceptSuggestions, imDeleteExample, imEditExample, imExamples, imGenerate, imGet, type Example } from "@/lib/intuition-api";
import { issuesOf, LabelChip, LabelPicker, labelSpace, PAIR_SPACE, type LabelSpace } from "@/components/wizard/labels";
import { useWizard } from "@/components/wizard/wizard-ui";
import UploaderCard from "@/components/wizard/cards/UploaderCard";
import GoldenCard from "@/components/wizard/cards/GoldenCard";
import LabelerCard from "@/components/wizard/cards/LabelerCard";
import { Badge, FilterChips, ItemRow } from "./ItemRow";

type Filter = "all" | "todo" | "held" | "pinned" | `label:${string}`;
const SUGGESTED = /^Suggested [^:]+: ?/;

function Editor({ example, space, onChanged }: { example: Example; space: LabelSpace; onChanged: () => void }) {
  const { modelId } = useWizard();
  const suggested = example.needs_review ? example.label : null;
  const [value, setValue] = useState<string | null>(example.label);
  const [note, setNote] = useState(SUGGESTED.test(example.note) || example.note.startsWith("Generated") ? "" : example.note);
  const [error, setError] = useState("");
  const run = (fn: () => Promise<unknown>) => fn().then(onChanged).catch((e) => setError(errorMessage(e)));
  return (
    <div className="space-y-2.5">
      {suggested && <p className="m-0 flex items-start gap-1.5 text-[12px]"><Sparkles className="mt-0.5 size-3 text-brand-500" /><span>{example.note.replace(SUGGESTED, "Suggested: ")}</span></p>}
      <LabelPicker space={example.kind === "pair" ? PAIR_SPACE : space} value={value} suggested={suggested} commitLabel="Save"
        onPick={(label, go) => { setValue(label); if (go && modelId) void run(() => imEditExample(modelId, example.id, { label, needs_review: false, note: note.trim() })); }} />
      <div className="flex flex-wrap items-center gap-2">
        <input aria-label="Why" value={note} onChange={(e) => setNote(e.target.value)} onBlur={() => { if (modelId && !example.needs_review && note.trim() !== example.note) void run(() => imEditExample(modelId, example.id, { note: note.trim() })); }} placeholder="Why this label? (optional)" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground/40" />
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
export default function ExamplesPanel() {
  const { modelId, refresh, send, version } = useWizard();
  const [examples, setExamples] = useState<Example[] | null>(null);
  const [space, setSpace] = useState<LabelSpace | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState<"" | "upload" | "generate" | "label">("");
  const [count, setCount] = useState(8);
  const [guidance, setGuidance] = useState("");
  const [propose, setPropose] = useState(true);
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

  async function generate() {
    if (!modelId) return;
    setBusy("Drafting examples…"); setError("");
    try {
      const made = await imGenerate(modelId, { count, guidance: guidance.trim(), propose });
      await load(); refresh(); setAdding("label");
      send(`Generated ${made.length} examples${propose ? " with suggested labels" : ""} to label.`, "event");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(""); }
  }

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
          <Button size="sm" variant={adding === "generate" ? "secondary" : "outline"} onClick={() => setAdding(adding === "generate" ? "" : "generate")}><Sparkles />Generate</Button>
          {todo.length > 0 && <Button size="sm" onClick={() => setAdding("label")}>Label {todo.length}</Button>}
        </div>
      </div>

      {adding === "upload" && <UploaderCard prompt="Add real examples, especially hard and borderline ones." />}
      {adding === "generate" && (
        <section aria-label="Generate examples" className="space-y-2.5 rounded-lg border border-border p-3.5">
          <p className="m-0 text-[12.5px]">Draft realistic, borderline inputs aimed at the boundaries between labels.</p>
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <label className="flex items-center gap-1.5">How many <input aria-label="How many" type="number" min={1} max={20} value={count} onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} className="w-14 rounded-md border border-border bg-background px-2 py-1" /></label>
            <input aria-label="Focus (optional)" value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="Focus (optional), e.g. refunds that mention a bug" className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1" />
          </div>
          <label className="flex items-start gap-2 text-[12px]"><input type="checkbox" className="mt-0.5" checked={propose} onChange={(e) => setPropose(e.target.checked)} /><span>Suggest a label for each, with a reason. You still confirm each one (or accept them all at once).</span></label>
          <Button size="sm" disabled={!!busy} onClick={() => void generate()}>{busy || "Generate"}</Button>
        </section>
      )}
      {adding === "label" && todo.length > 0 && (
        <div className="space-y-2">
          <LabelerCard key={todo.length} which="needs_review" />
          {suggestions.length > 0 && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void acceptAll()} title="Confirm every pending suggestion as is">Accept all {suggestions.length} suggestions</Button>}
        </div>
      )}

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
      <ul className="m-0 list-none space-y-2 p-0">
        {visible.slice(0, 200).map((e) => (
          <ItemRow
            key={e.id}
            item={e.item}
            itemB={e.item_b}
            open={open === e.id}
            onToggle={() => setOpen(open === e.id ? null : e.id)}
            badges={<>
              <Badge>{e.note.startsWith("Adversarial repair") ? "repair" : e.source === "production" ? "from inbox" : e.source === "generated" ? "generated" : "real"}</Badge>
              {e.split === "eval" && <Badge>held out</Badge>}
              {e.pinned && <Badge tone="brand">pinned</Badge>}
              {!e.needs_review && e.note && !e.note.startsWith("From prediction") && !e.note.startsWith("Generated") && !SUGGESTED.test(e.note) && <span className="truncate italic">“{e.note}”</span>}
            </>}
            decision={e.needs_review
              ? (e.label ? <><LabelChip label={e.label} kind={space?.kind} tone="muted" /><span className="text-[10.5px] text-brand-600 dark:text-brand-400">suggested</span></> : <Badge tone="warn">needs a label</Badge>)
              : <LabelChip label={e.label} kind={space?.kind} tone="you" />}
          >
            {space && <Editor example={e} space={space} onChanged={() => { void load(); refresh(); }} />}
          </ItemRow>
        ))}
      </ul>
    </div>
  );
}
