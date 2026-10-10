"use client";

import { Check, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { relativeTime } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import type { Example, Split } from "@/lib/intuition-api";
import { labelText } from "./im-helpers";
import { LabelTag, Segmented, SourceTag } from "./im-ui";
import ItemView from "./ItemView";

export interface ExampleRowProps {
  example: Example;
  labelOptions: string[];
  seed: boolean;
  seedDisabledReason: string | null;
  /** The head's prediction when it disagrees with the label. */
  mistake: string | null;
  highlighted?: boolean;
  onLabel: (label: string) => void;
  onSplit: (split: Split) => void;
  onToggleSeed: () => void;
  onConfirm: () => void;
  onDelete: () => void;
}

export default function ExampleRow({ example, labelOptions, seed, seedDisabledReason, mistake, highlighted, onLabel, onSplit, onToggleSeed, onConfirm, onDelete }: ExampleRowProps) {
  const kind = example.kind;
  const options = labelOptions.map((l) => ({ value: l, label: labelText(l, kind) }));
  return (
    <li
      id={`example-${example.id}`}
      className={cn(
        "rounded-lg border bg-background",
        example.needs_review ? "border-yellow-500/40" : "border-border",
        highlighted && "ring-2 ring-brand-400/50",
      )}
    >
      {example.needs_review && (
        <div className="flex flex-wrap items-center gap-2 border-b border-yellow-500/25 bg-yellow-500/6 px-4 py-1.5 text-[12px] text-yellow-900 dark:text-yellow-200">
          <span className="font-medium">Needs review</span>
          <span className="text-yellow-800/80 dark:text-yellow-200/80">
            {example.label ? (
              <>
                — suggested: <span className="font-mono">{labelText(example.label, kind)}</span>
              </>
            ) : (
              "— pick a label"
            )}
          </span>
          <span className="flex-1" />
          <Button size="xs" variant="outline" disabled={!example.label} onClick={onConfirm} title={example.label ? "Accept the suggested label" : "Choose a label first"}>
            <Check /> Confirm
          </Button>
        </div>
      )}
      <div className="grid gap-4 px-4 py-3 md:grid-cols-[minmax(0,1fr)_15rem]">
        <div className={cn("min-w-0", kind === "pair" && "grid gap-3 sm:grid-cols-2")}>
          {kind === "pair" ? (
            <>
              <PairSide tag="A" winner={example.label === "a"}>
                <ItemView item={example.item} />
              </PairSide>
              <PairSide tag="B" winner={example.label === "b"}>
                <ItemView item={example.item_b ?? ""} />
              </PairSide>
            </>
          ) : (
            <ItemView item={example.item} />
          )}
          {example.note && kind !== "pair" && <p className="m-0 mt-2 text-[11.5px] text-muted-foreground italic">{example.note}</p>}
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-center gap-1.5">
            <Select
              aria-label="Label"
              value={example.label ?? ""}
              onChange={onLabel}
              options={[...(example.label ? [] : [{ value: "", label: "Unlabeled" }]), ...options]}
              className="h-7 min-w-0 flex-1 px-2 font-mono text-[12px]"
            />
            <button
              type="button"
              aria-pressed={seed}
              aria-label={seed ? "Remove from seed examples" : "Use as a seed example"}
              title={seedDisabledReason ?? (seed ? "Seed: shown to the judge as a reference. Click to remove." : "Show to the judge as a reference example (seed)")}
              disabled={!seed && seedDisabledReason !== null}
              onClick={onToggleSeed}
              className={cn(
                "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                seed ? "border-brand-300 bg-brand-500/10 text-brand-600" : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              <Star className={cn("h-3.5 w-3.5", seed && "fill-current")} />
            </button>
          </div>
          <div className="flex items-center gap-1.5">
            <Segmented
              size="xs"
              ariaLabel="Split"
              value={example.split}
              onChange={onSplit}
              options={[
                { value: "train", label: "train" },
                { value: "eval", label: "held-out" },
              ]}
            />
            <span className="flex-1" />
            <Button size="icon-xs" variant="ghost" aria-label="Delete example" onClick={onDelete}>
              <Trash2 />
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
            <SourceTag source={example.source} />
            {mistake && <LabelTag tone="danger" label={`head says ${labelText(mistake, kind)}`} />}
            {seed && example.split === "eval" && <span title="Seeds are excluded from held-out evaluation">not scored</span>}
            <span className="ml-auto">{relativeTime(example.created_at)}</span>
          </div>
        </div>
      </div>
    </li>
  );
}

function PairSide({ tag, winner, children }: { tag: string; winner: boolean; children: React.ReactNode }) {
  return (
    <div className={cn("min-w-0 rounded-md border px-3 py-2", winner ? "border-emerald-500/40 bg-emerald-500/5" : "border-border-subtle")}>
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-dim">
        {tag}
        {winner && <span className="tag tag-success">better</span>}
      </div>
      {children}
    </div>
  );
}
