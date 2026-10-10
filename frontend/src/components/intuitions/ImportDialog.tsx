"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imAddExamples, type Example, type ExampleSource, type OutputLabel, type OutputType } from "@/lib/intuition-api";
import { parseJsonl } from "./im-helpers";
import { inputClass, Segmented, Spinner } from "./im-ui";

const CHUNK = 500;

export default function ImportDialog({
  open,
  onOpenChange,
  modelId,
  outputType,
  labels,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelId: string;
  outputType: OutputType;
  labels: OutputLabel[];
  onImported: (examples: Example[]) => void;
}) {
  const [text, setText] = useState("");
  const [source, setSource] = useState<Extract<ExampleSource, "human" | "agent">>("human");
  const [busy, setBusy] = useState(false);
  const parsed = useMemo(() => parseJsonl(text, outputType, labels), [text, outputType, labels]);
  const unlabeled = parsed.examples.filter((e) => e.needs_review).length;
  const example =
    outputType === "choice"
      ? `{"item": {"customer": "…", "reply": "…"}, "label": "${labels[0]?.id ?? "label"}"}\n{"item": "plain text works too", "split": "eval"}`
      : `{"item": "reply A", "item_b": "reply B", "label": "a"}\n{"item": "a single item", "label": "good"}`;

  async function submit() {
    setBusy(true);
    const created: Example[] = [];
    try {
      for (let i = 0; i < parsed.examples.length; i += CHUNK) {
        created.push(...(await imAddExamples(modelId, parsed.examples.slice(i, i + CHUNK), source)));
      }
      toast.success(`Imported ${created.length} example${created.length === 1 ? "" : "s"}`);
      setText("");
      onOpenChange(false);
    } catch (e) {
      toast.error(created.length ? `Imported ${created.length}, then failed: ${errorMessage(e)}` : errorMessage(e));
    } finally {
      if (created.length) onImported(created);
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import examples</DialogTitle>
          <DialogDescription>
            Paste JSONL, one object per line: <code className="font-mono text-[12px]">{"{item, item_b?, label?, split?}"}</code>. Lines without a label are imported as needing review.
          </DialogDescription>
        </DialogHeader>
        <textarea
          aria-label="JSONL"
          rows={10}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={example}
          spellCheck={false}
          className={`${inputClass} font-mono text-[12px] leading-relaxed`}
        />
        <div className="flex flex-wrap items-center gap-3 text-[12px]">
          <span className="text-dim">Source</span>
          <Segmented
            size="xs"
            ariaLabel="Source"
            value={source}
            onChange={setSource}
            options={[
              { value: "human", label: "human" },
              { value: "agent", label: "agent" },
            ]}
          />
          <span className="text-muted-foreground">
            {parsed.examples.length} ready{unlabeled ? ` (${unlabeled} unlabeled)` : ""}
            {parsed.errors.length ? ` · ${parsed.errors.length} skipped` : ""}
          </span>
        </div>
        {parsed.errors.length > 0 && (
          <ul className="m-0 max-h-28 list-none overflow-y-auto rounded-md border border-red-500/20 bg-red-500/5 p-2 font-mono text-[11.5px] text-red-700 dark:text-red-400">
            {parsed.errors.slice(0, 50).map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={busy || parsed.examples.length === 0}>
            {busy && <Spinner />}
            Import {parsed.examples.length || ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
