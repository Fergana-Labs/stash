"use client";

import { useState } from "react";
import { Lightbulb, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/reward-models/rm-ui";
import { errorMessage } from "@/components/reward-models/rm-text";
import { cn } from "@/lib/utils";
import { imDraftRubric, imSuggestQuestion, type RubricQuestion } from "@/lib/intuition-api";
import { inputClass, Panel, Segmented, Spinner } from "./im-ui";
import { QuestionPreview } from "./RubricEditor";

/** Claude proposes a starting rubric; the user picks questions to add or replace with. Nothing is saved here. */
export function DraftRubricDialog({
  open,
  onOpenChange,
  modelId,
  hasQuestions,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelId: string;
  hasQuestions: boolean;
  onApply: (questions: RubricQuestion[], mode: "add" | "replace") => void;
}) {
  const [count, setCount] = useState(5);
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<{ rationale: string; rubric: RubricQuestion[]; examples_considered: number } | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"add" | "replace">(hasQuestions ? "add" : "replace");

  async function propose(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    try {
      const res = await imDraftRubric(modelId, { count, guidance: guidance.trim() });
      setProposal(res);
      setPicked(new Set(res.rubric.map((q) => q.id)));
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function close(next: boolean) {
    if (busy) return;
    onOpenChange(next);
    if (!next) setProposal(null);
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Draft rubric with Claude</DialogTitle>
          <DialogDescription>Claude reads the description and your labeled examples and proposes questions for the judge. You choose what to keep; nothing is saved until you save the rubric.</DialogDescription>
        </DialogHeader>
        {!proposal ? (
          <form id="draft-rubric-form" onSubmit={(e) => void propose(e)} className="space-y-3">
            <Field label="How many questions" hint="1–12. Fewer, sharper questions generalize better on small data.">
              <input type="number" min={1} max={12} value={count} onChange={(e) => setCount(Math.max(1, Math.min(12, Number(e.target.value) || 1)))} className={cn(inputClass, "w-24 font-mono")} />
            </Field>
            <Field label="Guidance (optional)" hint="What should the questions focus on? E.g. “tone and promises we can’t keep”.">
              <textarea rows={3} value={guidance} onChange={(e) => setGuidance(e.target.value)} maxLength={2000} className={inputClass} />
            </Field>
          </form>
        ) : (
          <div className="max-h-[55vh] space-y-3 overflow-y-auto pr-1">
            <p className="m-0 rounded-md bg-surface/70 px-3 py-2 text-[12.5px] leading-relaxed text-dim">
              {proposal.rationale}
              <span className="mt-1 block text-[11px] text-muted-foreground">Considered {proposal.examples_considered} examples.</span>
            </p>
            <ul className="m-0 list-none space-y-1.5 p-0">
              {proposal.rubric.map((q) => (
                <li key={q.id}>
                  <label className={cn("flex gap-2.5 rounded-md border px-3 py-2", picked.has(q.id) ? "border-brand-300/70 bg-brand-500/4" : "border-border")}>
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-brand-500"
                      checked={picked.has(q.id)}
                      onChange={(e) =>
                        setPicked((s) => {
                          const next = new Set(s);
                          if (e.target.checked) next.add(q.id);
                          else next.delete(q.id);
                          return next;
                        })
                      }
                    />
                    <QuestionPreview q={q} className="flex-1" />
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
        <DialogFooter className="items-center">
          {proposal && hasQuestions && (
            <div className="mr-auto">
              <Segmented
                size="xs"
                ariaLabel="Apply mode"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "add", label: "Add to rubric" },
                  { value: "replace", label: "Replace rubric" },
                ]}
              />
            </div>
          )}
          {proposal ? (
            <>
              <Button variant="outline" onClick={() => setProposal(null)}>
                Back
              </Button>
              <Button
                disabled={picked.size === 0}
                onClick={() => {
                  onApply(
                    proposal.rubric.filter((q) => picked.has(q.id)),
                    hasQuestions ? mode : "replace",
                  );
                  close(false);
                }}
              >
                Use {picked.size} question{picked.size === 1 ? "" : "s"}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => close(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" form="draft-rubric-form" disabled={busy}>
                {busy ? <Spinner /> : <Sparkles />}
                {busy ? "Drafting…" : "Draft questions"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** One new question aimed at the current head's mistakes. */
export function SuggestQuestion({ modelId, disabledReason, onAdd }: { modelId: string; disabledReason: string | null; onAdd: (q: RubricQuestion) => Promise<void> | void }) {
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [suggestion, setSuggestion] = useState<{ rationale: string; question: RubricQuestion; mistakes_considered: number } | null>(null);

  async function suggest() {
    setBusy(true);
    try {
      setSuggestion(await imSuggestQuestion(modelId));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!suggestion) {
    return (
      <Button variant="outline" size="sm" onClick={() => void suggest()} disabled={busy || disabledReason !== null} title={disabledReason ?? "Claude looks at what the head gets wrong and proposes one new question"}>
        {busy ? <Spinner /> : <Lightbulb />}
        Suggest a question from mistakes
      </Button>
    );
  }

  return (
    <Panel
      className="w-full"
      title="Suggested question"
      description={`From ${suggestion.mistakes_considered} mistake${suggestion.mistakes_considered === 1 ? "" : "s"}.`}
      actions={
        <>
          <Button size="xs" variant="ghost" onClick={() => setSuggestion(null)}>
            Dismiss
          </Button>
          <Button size="xs" variant="ghost" onClick={() => void suggest()} disabled={busy}>
            {busy && <Spinner className="h-3 w-3" />}
            Another
          </Button>
          <Button
            size="xs"
            disabled={adding}
            onClick={async () => {
              setAdding(true);
              try {
                await onAdd(suggestion.question);
                setSuggestion(null);
              } finally {
                setAdding(false);
              }
            }}
          >
            {adding && <Spinner className="h-3 w-3" />}
            Add to draft
          </Button>
        </>
      }
    >
      <p className="m-0 mb-2.5 text-[12.5px] leading-relaxed text-dim">{suggestion.rationale}</p>
      <QuestionPreview q={suggestion.question} className="rounded-md border border-border-subtle px-3 py-2" />
    </Panel>
  );
}
