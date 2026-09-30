"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { rmGetRewardModel } from "@/lib/api";
import type { RmRewardModelDetail } from "@/lib/types";
import { errorMessage } from "./rm-text";

export default function FeedbackDialog({ modelId }: { modelId: string }) {
  const [model, setModel] = useState<RmRewardModelDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(open: boolean) {
    if (!open) return;
    setModel(null);
    setError(null);
    try {
      setModel(await rmGetRewardModel(modelId));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Dialog onOpenChange={(open) => void load(open)}>
      <DialogTrigger asChild><Button variant="outline" size="xs">View feedback</Button></DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Inferred feedback</DialogTitle>
          <DialogDescription>
            Judgments inferred from user reactions and reviewer comments, not human ratings.
            Training pairs compare the original response with a generated alternative in the same context.
          </DialogDescription>
        </DialogHeader>
        {error ? <p role="alert">{error}</p> : model === null ? <p role="status">Loading feedback…</p> : model.feedback === null ? (
          <p>No feedback report was recorded for this model.</p>
        ) : model.feedback.length === 0 ? (
          <p>No supported feedback was found in the selected traces.</p>
        ) : (
          <ol className="m-0 list-none divide-y divide-border p-0">
            {model.feedback.map((item) => (
              <li key={`${item.trace_id}:${item.step_index}`} className="py-4 first:pt-0">
                <div className="flex items-baseline justify-between gap-4 text-sm">
                  <span className="font-medium capitalize">{item.label}</span>
                  <Link href={`/reward-models/traces/${item.trace_id}`} className="text-muted-foreground underline underline-offset-2">
                    Response at step {item.step_index + 1}
                  </Link>
                </div>
                <blockquote className="mx-0 my-3 border-l-2 border-border pl-3 text-sm">{item.evidence_quote}</blockquote>
                <p className="m-0 text-sm">{item.reason}</p>
                <p className="mb-0 mt-2 text-xs text-muted-foreground">
                  {item.included_in_training ? "Included in training data" : "Excluded from training"}
                  {" · "}{item.confidence === "high" ? "High" : "Low"} classifier confidence
                  {" · "}{item.classifier_model}
                </p>
              </li>
            ))}
          </ol>
        )}
      </DialogContent>
    </Dialog>
  );
}
