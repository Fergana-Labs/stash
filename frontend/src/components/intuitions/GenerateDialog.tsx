"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imGenerate, type Example } from "@/lib/intuition-api";
import { inputClass, Spinner } from "./im-ui";

/** Ask Claude for new items; they arrive flagged needs_review with a suggested label. */
export default function GenerateDialog({ open, onOpenChange, modelId, onGenerated }: { open: boolean; onOpenChange: (open: boolean) => void; modelId: string; onGenerated: (examples: Example[]) => void }) {
  const [count, setCount] = useState(6);
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await imGenerate(modelId, { count, guidance: guidance.trim() });
      onGenerated(created);
      toast.success(`Generated ${created.length} example${created.length === 1 ? "" : "s"} to review`);
      onOpenChange(false);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={(e) => void submit(e)} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Generate examples</DialogTitle>
            <DialogDescription>
              Claude writes new items like your existing ones. They’re marked “needs review” with the current model’s suggested label — confirm or correct each before it counts.
            </DialogDescription>
          </DialogHeader>
          <Field label="How many" hint="1–20">
            <input type="number" min={1} max={20} value={count} onChange={(e) => setCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))} className={`${inputClass} w-24 font-mono`} />
          </Field>
          <Field label="Guidance (optional)" hint="E.g. “borderline cases between edit and rewrite”, “replies that promise refunds”.">
            <textarea rows={3} value={guidance} onChange={(e) => setGuidance(e.target.value)} maxLength={2000} className={inputClass} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy && <Spinner />}
              {busy ? "Generating…" : "Generate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
