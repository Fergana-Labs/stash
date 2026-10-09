"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TrainPanel";

import { useEffect, useState } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
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
 * "Options" exposes them. A selection needs at least two source traces;
 * the server validates the resulting training/evaluation split.
 */
function LatestTrainPanel({
  traceIds,
  summary,
  onTrained,
  optionsPlacement,
  modelName,
}: {
  traceIds: string[];
  summary: SelectionSummary;
  onTrained: (model: RmRewardModel) => void;
  /** Where the Options popover opens: below for a bar at the top, above for a footer. */
  optionsPlacement: "above" | "below";
  /** Name supplied by the creation dialog; standalone panels generate their own default. */
  modelName?: string;
}) {
  const [modelCount, setModelCount] = useState<number | null>(null);
  const [showOptions, setShowOptions] = useState(false);
  // null = the generated name, which follows the model count.
  const [nameOverride, setNameOverride] = useState<string | null>(null);
  const [baseModel, setBaseModel] = useState(DEFAULT_BASE_MODEL);
  const [customBaseModel, setCustomBaseModel] = useState(false);
  const [epochs, setEpochs] = useState(1);
  const [rubric, setRubric] = useState("Task completion\nAdherence to the user's constraints\nEvidence grounding\nAppropriate uncertainty");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (modelName !== undefined) return;
    rmListRewardModels()
      .then((models) => setModelCount(models.length))
      .catch((e) => toast.error(errorMessage(e)));
  }, [modelName]);

  const name = modelName ?? nameOverride ?? (modelCount === null ? "" : `reward-model-${modelCount + 1}`);

  async function train() {
    setSubmitting(true);
    setError(null);
    try {
      const model = await rmCreateRewardModel({
        trace_ids: traceIds,
        name: name.trim(),
        base_model: baseModel.trim(),
        epochs,
        training_config: { input_version: 3, annotation_source: "automatic", rubric: rubric.split("\n").map((line) => line.trim()).filter(Boolean) },
      });
      onTrained(model);
    } catch (e) {
      setError(errorMessage(e));
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-w-0 flex-col items-end gap-2">
      <TrainStatus summary={summary} error={error} />
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
          <span>Base model</span>
          <div className="flex flex-col gap-1">
            <Select aria-label="Base model" value={customBaseModel ? "custom" : baseModel} onChange={(value) => {
              setCustomBaseModel(value === "custom");
              setBaseModel(value === "custom" ? "" : value);
            }} options={[...BASE_MODEL_SUGGESTIONS.map((value) => ({ value, label: value })), { value: "custom", label: "Custom model…" }]} className="h-8 w-48 px-2 text-[12px]" />
            {customBaseModel && <Input aria-label="Custom base model" value={baseModel} onChange={(e) => setBaseModel(e.target.value)} placeholder="Hugging Face model ID" className="h-8 w-48 text-[12px]" />}
          </div>
        </div>
        <Button variant="outline" onClick={() => setShowOptions(!showOptions)} aria-expanded={showOptions}>
          Options
          <ChevronDown className={cn("transition-transform", showOptions && "rotate-180")} />
        </Button>
        <Button onClick={() => void train()} disabled={submitting || traceIds.length < 2 || !name.trim() || !baseModel.trim()}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitting ? "Queuing…" : "Create new reward model"}
        </Button>
      </div>

      {showOptions && (
        <div
          className={cn(
            "absolute right-0 z-30 flex w-80 flex-col gap-3 rounded-lg border border-border bg-popover p-4 text-left shadow-lg",
            optionsPlacement === "below" ? "top-full mt-2" : "bottom-full mb-2",
          )}
        >
          {modelName === undefined && (
            <Field label="Model name">
              <Input value={name} onChange={(e) => setNameOverride(e.target.value)} />
            </Field>
          )}
          <Field label="Reward criteria (one per line)">
            <textarea aria-label="Reward criteria" value={rubric} onChange={(e) => setRubric(e.target.value)} rows={5} className="w-full rounded border border-border bg-background p-2 text-sm" />
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
  if (error) return <p role="alert" className="m-0 max-w-sm text-right text-[12px] leading-snug text-red-600">{error}</p>;
  if (summary.count > 1) return null;
  return (
    <p className="m-0 max-w-xs text-right text-[12px] leading-snug text-amber-700 dark:text-amber-400">
      Select at least two traces. Training and evaluation use separate traces.
    </p>
  );
}

export default function TrainPanel(props: React.ComponentProps<typeof LatestTrainPanel>) {
  return useProductCheckpoint() === "floodgate-2026-10-05"
    ? <FloodgateComponent {...props} />
    : <LatestTrainPanel {...props} />;
}
