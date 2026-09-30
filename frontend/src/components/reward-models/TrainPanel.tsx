"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { rmCreateRewardModel, rmListRewardModels } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { RmRewardModel } from "@/lib/types";
import { Field } from "./rm-ui";
import { errorMessage } from "./rm-text";
import { type SelectionSummary } from "./trace-selection";

const DEFAULT_BASE_MODEL = "Qwen/Qwen3-0.6B";
const BASE_MODEL_SUGGESTIONS = ["Qwen/Qwen3-0.6B", "Qwen/Qwen3-1.7B", "Qwen/Qwen3-4B", "HuggingFaceTB/SmolLM2-360M-Instruct"];

/**
 * Trains a reward model on exactly `traceIds`. One click uses the defaults;
 * "Options" exposes them. The button is disabled only while the request is in
 * flight: a selection that can't train says why beside it, and the server's
 * error is shown inline if the user trains anyway.
 */
export default function TrainPanel({
  traceIds,
  summary,
  onTrained,
  optionsPlacement,
}: {
  traceIds: string[];
  summary: SelectionSummary;
  onTrained: (model: RmRewardModel) => void;
  /** Where the Options popover opens: below for a bar at the top, above for a footer. */
  optionsPlacement: "above" | "below";
}) {
  const [modelCount, setModelCount] = useState<number | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  // null = the generated name, which follows the model count.
  const [nameOverride, setNameOverride] = useState<string | null>(null);
  const [baseModel, setBaseModel] = useState(DEFAULT_BASE_MODEL);
  const [epochs, setEpochs] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    rmListRewardModels()
      .then((models) => setModelCount(models.length))
      .catch((e) => toast.error(errorMessage(e)));
  }, []);

  const name = nameOverride ?? (modelCount === null ? "" : `reward-model-${modelCount + 1}`);

  async function train() {
    setSubmitting(true);
    setError(null);
    try {
      const model = await rmCreateRewardModel({
        trace_ids: traceIds,
        name: name.trim(),
        base_model: baseModel.trim(),
        epochs,
      });
      onTrained(model);
    } catch (e) {
      setError(errorMessage(e));
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex items-center gap-3">
      <TrainStatus summary={summary} error={error} />
      <label className="flex items-center gap-2 text-[12px] text-muted-foreground">
        Base model
        <Input
          value={baseModel}
          onChange={(e) => setBaseModel(e.target.value)}
          list="rm-base-models"
          title="Any Hugging Face model that loads with AutoModelForSequenceClassification."
          className="h-8 w-48 font-mono text-[12.5px] text-foreground md:text-[12.5px]"
        />
        <datalist id="rm-base-models">
          {BASE_MODEL_SUGGESTIONS.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </label>
      <Button variant="outline" onClick={() => setShowOptions(!showOptions)} aria-expanded={showOptions}>
        Options
        <ChevronDown className={cn("transition-transform", showOptions && "rotate-180")} />
      </Button>
      <Button onClick={() => void train()} disabled={submitting}>
        {submitting && <Loader2 className="animate-spin" />}
        {submitting ? "Queuing…" : "Create new reward model"}
      </Button>

      {showOptions && (
        <div
          className={cn(
            "absolute right-0 z-30 flex w-80 flex-col gap-3 rounded-lg border border-border bg-popover p-4 text-left shadow-lg",
            optionsPlacement === "below" ? "top-full mt-2" : "bottom-full mb-2",
          )}
        >
          <Field label="Name">
            <Input value={name} onChange={(e) => setNameOverride(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Epochs">
              <Input type="number" min={1} max={20} value={epochs} onChange={(e) => setEpochs(Number(e.target.value))} />
            </Field>
          </div>

        </div>
      )}
    </div>
  );
}

function TrainStatus({ summary, error }: { summary: SelectionSummary; error: string | null }) {
  if (error) return <p className="m-0 max-w-sm text-right text-[12px] leading-snug text-red-600">{error}</p>;
  if (summary.count > 0) return null;
  return (
    <p className="m-0 max-w-xs text-right text-[12px] leading-snug text-amber-700 dark:text-amber-400">
      Select traces to train a model.
    </p>
  );
}
