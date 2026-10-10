"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imCreate, type OutputLabel, type OutputType } from "@/lib/intuition-api";
import { rubricProblem } from "./im-helpers";
import { inputClass, Segmented, Spinner } from "./im-ui";
import LabelsEditor from "./LabelsEditor";

const STARTER_LABELS: OutputLabel[] = [
  { id: "yes", description: "" },
  { id: "no", description: "" },
];

export default function CreateModelDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [outputType, setOutputType] = useState<OutputType>("choice");
  const [description, setDescription] = useState("");
  const [labels, setLabels] = useState<OutputLabel[]>(STARTER_LABELS);
  const [busy, setBusy] = useState(false);

  const problem = !name.trim() ? "Name the model" : rubricProblem(outputType, outputType === "choice" ? labels : [], []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (problem) return;
    setBusy(true);
    try {
      const detail = await imCreate({
        name: name.trim(),
        output_type: outputType,
        description: description.trim(),
        labels: outputType === "choice" ? labels : [],
      });
      toast.success(`Created ${detail.model.name}`);
      router.push(`/reward-models/intuitions/${detail.model.id}?tab=rubric`);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={(e) => void create(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New intuition model</DialogTitle>
            <DialogDescription>A personal judge that learns your taste from labeled examples.</DialogDescription>
          </DialogHeader>
          <Field label="Name">
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Support reply: ready to send?" className={inputClass} maxLength={160} />
          </Field>
          <div>
            <span className="mb-1 block text-[12px] font-medium text-dim">Output</span>
            <Segmented
              ariaLabel="Output type"
              value={outputType}
              onChange={setOutputType}
              options={[
                { value: "choice", label: "Choice — sort into labels" },
                { value: "preference", label: "Preference — learn a score" },
              ]}
            />
            <p className="m-0 mt-1 text-[11.5px] text-muted-foreground">
              {outputType === "choice"
                ? "Classifies each item into one of your labels (e.g. send / edit / rewrite)."
                : "Learns a scalar score from “A is better than B” comparisons and good/bad items."}
            </p>
          </div>
          <Field label="Description" hint="What is being judged and what you care about. The judge reads this with every question.">
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Drafted replies from our support agent, judged the way our support lead reviews them…"
              className={inputClass}
              maxLength={6000}
            />
          </Field>
          {outputType === "choice" && (
            <div>
              <span className="mb-1 block text-[12px] font-medium text-dim">Labels</span>
              <LabelsEditor value={labels} onChange={setLabels} disabled={busy} />
            </div>
          )}
          <DialogFooter className="items-center">
            {problem && name.trim() && <span className="mr-auto text-[12px] text-red-600 dark:text-red-400">{problem}</span>}
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || problem !== null}>
              {busy && <Spinner />}
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
