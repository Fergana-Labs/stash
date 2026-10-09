"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imAddExamples, type Example, type NewExample, type OutputLabel, type OutputType, type Split } from "@/lib/intuition-api";
import { allowedLabels, labelText } from "./im-helpers";
import { Panel, Segmented, Spinner } from "./im-ui";
import ItemInput, { draftToItem, emptyDraft, type ItemDraft } from "./ItemInput";

type Mode = "item" | "pair";

/** Add one labeled example. Fields mirror the model's item shape. */
export default function AddExampleForm({
  modelId,
  outputType,
  labels,
  keys,
  onAdded,
  onClose,
}: {
  modelId: string;
  outputType: OutputType;
  labels: OutputLabel[];
  keys: string[] | null;
  onAdded: (examples: Example[]) => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<Mode>(outputType === "preference" ? "pair" : "item");
  const [a, setA] = useState<ItemDraft>(emptyDraft);
  const [b, setB] = useState<ItemDraft>(emptyDraft);
  const [label, setLabel] = useState<string>("");
  const [split, setSplit] = useState<"auto" | Split>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options = allowedLabels(outputType, mode, labels);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const item = draftToItem(a, keys);
    if ("error" in item) return setError(mode === "pair" ? `Item A: ${item.error}` : item.error);
    const body: NewExample = { item: item.item, label };
    if (mode === "pair") {
      const itemB = draftToItem(b, keys);
      if ("error" in itemB) return setError(`Item B: ${itemB.error}`);
      body.item_b = itemB.item;
    }
    if (!label) return setError("Choose a label");
    if (split !== "auto") body.split = split;
    setBusy(true);
    setError(null);
    try {
      const created = await imAddExamples(modelId, [body]);
      onAdded(created);
      toast.success(`Added to ${created[0]?.split === "eval" ? "held-out" : "train"}`);
      setA(emptyDraft());
      setB(emptyDraft());
      setLabel("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Add example"
      actions={
        outputType === "preference" ? (
          <Segmented
            size="xs"
            ariaLabel="Example kind"
            value={mode}
            onChange={(m) => {
              setMode(m);
              setLabel("");
            }}
            options={[
              { value: "pair", label: "Pair: A vs B" },
              { value: "item", label: "Single: good / bad" },
            ]}
          />
        ) : undefined
      }
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <div className={mode === "pair" ? "grid gap-3 md:grid-cols-2" : ""}>
          <ItemInput keys={keys} value={a} onChange={setA} label={mode === "pair" ? "Item A" : undefined} disabled={busy} rows={3} onSubmit={() => void submit()} />
          {mode === "pair" && <ItemInput keys={keys} value={b} onChange={setB} label="Item B" disabled={busy} rows={3} onSubmit={() => void submit()} />}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Label">
            <span className="mr-1 text-[12px] font-medium text-dim">{mode === "pair" ? "Winner" : "Label"}</span>
            {options.map((l) => (
              <Button key={l} type="button" size="xs" role="radio" aria-checked={label === l} variant={label === l ? "default" : "outline"} onClick={() => setLabel(l)}>
                {labelText(l, mode)}
              </Button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[12px] font-medium text-dim">Split</span>
            <Segmented
              size="xs"
              ariaLabel="Split"
              value={split}
              onChange={setSplit}
              options={[
                { value: "auto", label: "auto" },
                { value: "train", label: "train" },
                { value: "eval", label: "held-out" },
              ]}
            />
          </div>
          <span className="flex-1" />
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            Close
          </Button>
          <Button type="submit" size="sm" disabled={busy}>
            {busy && <Spinner />}
            Add example
          </Button>
        </div>
        {error && <p className="m-0 text-[12px] text-red-600 dark:text-red-400">{error}</p>}
        <p className="m-0 text-[11.5px] text-muted-foreground">“auto” puts about a quarter of examples in the held-out split, deterministically by content.</p>
      </form>
    </Panel>
  );
}
