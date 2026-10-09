"use client";

import { useProductCheckpoint } from "@/components/ProductCheckpointContext";
import FloodgateComponent from "@/checkpoints/floodgate-2026-10-05/TrainPanel";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { rmCreateRewardModel } from "@/lib/api";
import type { RmRewardModel } from "@/lib/types";
import { Field } from "./rm-ui";
import { errorMessage } from "./rm-text";
import { type SelectionSummary } from "./trace-selection";

/** Train on the selected traces using server-managed model and training defaults. */
function LatestTrainPanel({
  traceIds,
  summary,
  onTrained,
  modelName,
}: {
  traceIds: string[];
  summary: SelectionSummary;
  onTrained: (model: RmRewardModel) => void;
  /** Retained for the frozen checkpoint’s Options popover. */
  optionsPlacement: "above" | "below";
  /** The sheet supplies its name; standalone panels show a name field. */
  modelName?: string;
}) {
  const [nameOverride, setNameOverride] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const name = modelName ?? nameOverride;

  async function train() {
    setSubmitting(true);
    setError(null);
    try {
      const model = await rmCreateRewardModel({
        trace_ids: traceIds,
        name: name.trim(),
        training_config: { input_version: 3, annotation_source: "automatic" },
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
      <div className="flex flex-wrap items-end justify-end gap-3">
        {modelName === undefined && <Field label="Model name">
          <Input value={name} onChange={(e) => setNameOverride(e.target.value)} placeholder="e.g. Parts accuracy" disabled={submitting} className="w-56" />
        </Field>}
        <Button onClick={() => void train()} disabled={submitting || traceIds.length < 2 || !name.trim()}>
          {submitting && <Loader2 className="animate-spin" />}
          {submitting ? "Queuing…" : "Create new reward model"}
        </Button>
      </div>
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
