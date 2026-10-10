"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileUp, Plus, Search, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { RmListSkeleton } from "@/components/reward-models/RmSkeletons";
import { EmptyState } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imDeleteExample, imEditDraft, imEditExample, type Example, type ExampleSource, type Split } from "@/lib/intuition-api";
import { allowedLabels, detectItemKeys, itemsOf, itemSummary, labelText, MAX_SEEDS, mistakeIds, predictedById } from "./im-helpers";
import { ConfirmDialog, inputClass, LoadError, useIntuition } from "./im-ui";
import AddExampleForm from "./AddExampleForm";
import ExampleRow from "./ExampleRow";
import GenerateDialog from "./GenerateDialog";
import ImportDialog from "./ImportDialog";

const PAGE = 60;
const SOURCES: ExampleSource[] = ["human", "agent", "generated", "production"];

function Toggle({ on, onClick, children, disabled, title }: { on: boolean; onClick: () => void; children: React.ReactNode; disabled?: boolean; title?: string }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        on ? "border-brand-300 bg-brand-500/10 text-brand-600" : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export default function ExamplesTab() {
  const { id, detail, version, apply, examples, examplesError, setExamples, reloadExamples, reload, goTo } = useIntuition();
  const params = useSearchParams();
  const focusId = params.get("example");
  const outputType = detail.model.output_type;
  const labels = useMemo(() => version?.labels ?? [], [version]);

  const [query, setQuery] = useState("");
  const [split, setSplit] = useState<"" | Split>("");
  const [source, setSource] = useState<"" | ExampleSource>(() => (SOURCES as string[]).includes(params.get("source") ?? "") ? (params.get("source") as ExampleSource) : "");
  const [label, setLabel] = useState("");
  const [needsReview, setNeedsReview] = useState(params.get("filter") === "needs_review");
  const [mistakesOnly, setMistakesOnly] = useState(params.get("filter") === "mistakes");
  const [seedsOnly, setSeedsOnly] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [deleting, setDeleting] = useState<Example | null>(null);

  const keys = useMemo(() => detectItemKeys(itemsOf(examples ?? [])), [examples]);
  const mistakes = useMemo(() => mistakeIds(version?.metrics), [version]);
  const predicted = useMemo(() => predictedById(version?.metrics), [version]);
  const seeds = useMemo(() => new Set(version?.seed_example_ids ?? []), [version]);
  const labelFilterOptions = useMemo(() => {
    const all = outputType === "choice" ? labels.map((l) => l.id) : ["good", "bad", "a", "b"];
    return [{ value: "", label: "Any label" }, ...all.map((l) => ({ value: l, label: l === "a" || l === "b" ? labelText(l, "pair") : l })), { value: "__none__", label: "Unlabeled" }];
  }, [outputType, labels]);

  useEffect(() => {
    if (!focusId || !examples) return;
    document.getElementById(`example-${focusId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focusId, examples]);

  const visible = useMemo(() => {
    if (!examples) return [];
    if (focusId) return examples.filter((e) => e.id === focusId);
    const q = query.trim().toLowerCase();
    return examples.filter(
      (e) =>
        (!split || e.split === split) &&
        (!source || e.source === source) &&
        (!label || (label === "__none__" ? e.label === null : e.label === label)) &&
        (!needsReview || e.needs_review) &&
        (!mistakesOnly || mistakes.has(e.id)) &&
        (!seedsOnly || seeds.has(e.id)) &&
        (!q || itemSummary(e.item).toLowerCase().includes(q) || (e.item_b != null && itemSummary(e.item_b).toLowerCase().includes(q))),
    );
  }, [examples, focusId, query, split, source, label, needsReview, mistakesOnly, seedsOnly, mistakes, seeds]);

  const total = examples?.length ?? 0;
  const reviewCount = examples?.filter((e) => e.needs_review).length ?? 0;
  const heldOut = examples?.filter((e) => e.split === "eval").length ?? 0;

  function replace(updated: Example) {
    setExamples((list) => list?.map((e) => (e.id === updated.id ? updated : e)) ?? null);
  }

  async function edit(example: Example, body: { label?: string; split?: Split; needs_review?: boolean }) {
    replace({ ...example, ...body });
    try {
      replace(await imEditExample(id, example.id, body));
      void reload();
    } catch (e) {
      replace(example);
      toast.error(errorMessage(e));
    }
  }

  async function toggleSeed(example: Example) {
    if (!version) return;
    const current = version.seed_example_ids;
    const next = current.includes(example.id) ? current.filter((s) => s !== example.id) : [...current, example.id];
    try {
      apply(await imEditDraft(id, { seed_example_ids: next }));
      toast.success(next.length > current.length ? "Added as a seed" : "Removed from seeds", { description: "Seeds are part of every question’s context, so the draft will re-grade all examples." });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  function seedDisabledReason(e: Example): string | null {
    if (e.needs_review) return "Review this example before using it as a seed";
    if (!e.label) return "Label this example before using it as a seed";
    if (seeds.size >= MAX_SEEDS) return `At most ${MAX_SEEDS} seed examples`;
    return null;
  }

  function added(created: Example[]) {
    setExamples((list) => [...created, ...(list ?? [])]);
    void reload();
  }

  const anyFilter = !!(query || split || source || label || needsReview || mistakesOnly || seedsOnly);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="m-0 mr-auto text-[12.5px] text-muted-foreground">
          <span className="font-mono text-foreground">{total}</span> examples · <span className="font-mono">{total - heldOut}</span> train ·{" "}
          <span className="font-mono">{heldOut}</span> held-out · <span className="font-mono">{seeds.size}</span>/{MAX_SEEDS} seeds
          {reviewCount > 0 && (
            <>
              {" · "}
              <button type="button" className="text-yellow-700 underline underline-offset-2 dark:text-yellow-400" onClick={() => setNeedsReview(true)}>
                {reviewCount} need review
              </button>
            </>
          )}
        </p>
        <Button variant="outline" size="sm" onClick={() => setGenerating(true)}>
          <Sparkles /> Generate
        </Button>
        <Button variant="outline" size="sm" onClick={() => setImporting(true)}>
          <FileUp /> Import JSONL
        </Button>
        <Button size="sm" onClick={() => setAdding((v) => !v)} aria-expanded={adding}>
          <Plus /> Add example
        </Button>
      </div>

      {adding && <AddExampleForm modelId={id} outputType={outputType} labels={labels} keys={keys} onAdded={added} onClose={() => setAdding(false)} />}

      {focusId ? (
        <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
          Showing one example.
          <Button size="xs" variant="outline" onClick={() => goTo("examples")}>
            <X /> Show all
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="relative w-56">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input aria-label="Search examples" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search" className={cn(inputClass, "h-7 py-0 pl-8 text-[12px]")} />
          </div>
          <Select
            aria-label="Split"
            value={split}
            onChange={(v) => setSplit(v as "" | Split)}
            options={[
              { value: "", label: "Any split" },
              { value: "train", label: "Train" },
              { value: "eval", label: "Held-out" },
            ]}
            className="h-7 px-2 text-[12px]"
          />
          <Select aria-label="Source" value={source} onChange={(v) => setSource(v as "" | ExampleSource)} options={[{ value: "", label: "Any source" }, ...SOURCES.map((s) => ({ value: s, label: s }))]} className="h-7 px-2 text-[12px]" />
          <Select aria-label="Label" value={label} onChange={setLabel} options={labelFilterOptions} className="h-7 px-2 text-[12px]" />
          <Toggle on={needsReview} onClick={() => setNeedsReview((v) => !v)}>
            Needs review{reviewCount ? ` · ${reviewCount}` : ""}
          </Toggle>
          <Toggle on={mistakesOnly} onClick={() => setMistakesOnly((v) => !v)} disabled={!version?.metrics} title={version?.metrics ? "Examples the current head gets wrong" : "Fit the head to find mistakes"}>
            Mistakes{version?.metrics ? ` · ${mistakes.size}` : ""}
          </Toggle>
          <Toggle on={seedsOnly} onClick={() => setSeedsOnly((v) => !v)}>
            ★ Seeds
          </Toggle>
          {anyFilter && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => {
                setQuery("");
                setSplit("");
                setSource("");
                setLabel("");
                setNeedsReview(false);
                setMistakesOnly(false);
                setSeedsOnly(false);
              }}
            >
              Clear
            </Button>
          )}
        </div>
      )}

      {examplesError !== null && examples === null ? (
        <LoadError what="examples" message={examplesError} onRetry={() => void reloadExamples()} />
      ) : examples === null ? (
        <RmListSkeleton />
      ) : total === 0 ? (
        <EmptyState title="No examples yet">
          Examples teach the head what you think. Add a few by hand, import JSONL, or generate some to label. Aim for a handful per label, with some in held-out.
        </EmptyState>
      ) : visible.length === 0 ? (
        <EmptyState title="No examples match these filters" />
      ) : (
        <>
          <ul className="m-0 list-none space-y-2 p-0">
            {visible.slice(0, limit).map((e) => {
              const p = predicted.get(e.id);
              return (
                <ExampleRow
                  key={e.id}
                  example={e}
                  labelOptions={allowedLabels(outputType, e.kind, labels)}
                  seed={seeds.has(e.id)}
                  seedDisabledReason={seedDisabledReason(e)}
                  mistake={mistakes.has(e.id) && p ? p : null}
                  highlighted={e.id === focusId}
                  onLabel={(l) => l && void edit(e, e.needs_review ? { label: l, needs_review: false } : { label: l })}
                  onSplit={(s) => void edit(e, { split: s })}
                  onToggleSeed={() => void toggleSeed(e)}
                  onConfirm={() => void edit(e, { needs_review: false })}
                  onDelete={() => setDeleting(e)}
                />
              );
            })}
          </ul>
          {visible.length > limit && (
            <div className="flex justify-center">
              <Button variant="outline" size="sm" onClick={() => setLimit((n) => n + PAGE)}>
                Show more ({visible.length - limit} left)
              </Button>
            </div>
          )}
        </>
      )}

      <ImportDialog open={importing} onOpenChange={setImporting} modelId={id} outputType={outputType} labels={labels} onImported={added} />
      <GenerateDialog
        open={generating}
        onOpenChange={setGenerating}
        modelId={id}
        onGenerated={(created) => {
          added(created);
          setNeedsReview(true);
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title="Delete this example?"
        description="It’s removed from training and evaluation for every version. Cached judge answers are kept."
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          const target = deleting;
          if (!target) return;
          try {
            await imDeleteExample(id, target.id);
            setExamples((list) => list?.filter((e) => e.id !== target.id) ?? null);
            void reload();
          } catch (e) {
            toast.error(errorMessage(e));
          }
        }}
      />
    </div>
  );
}
