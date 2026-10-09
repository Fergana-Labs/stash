"use client";

import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imEditDraft, type OutputLabel, type RubricQuestion } from "@/lib/intuition-api";
import { invalidatedQuestions, rubricProblem, uniqueSlug } from "./im-helpers";
import { Callout, inputClass, Panel, Spinner, useIntuition } from "./im-ui";
import LabelsEditor from "./LabelsEditor";
import RubricEditor, { editProblem, fromEdit, newQuestion, toEdit, type EditQuestion } from "./RubricEditor";
import { DraftRubricDialog, SuggestQuestion } from "./RubricAssist";

export default function RubricTab() {
  const { version } = useIntuition();
  // Remount the form whenever the saved spec changes, so local edits always start from the server.
  const key = version ? `${version.id}:${JSON.stringify([version.description, version.labels, version.rubric])}` : "none";
  return <RubricForm key={key} />;
}

function RubricForm() {
  const { id, detail, version, apply } = useIntuition();
  const outputType = detail.model.output_type;
  const base = useMemo(() => ({ description: version?.description ?? "", labels: version?.labels ?? [], rubric: version?.rubric ?? [] }), [version]);
  const [description, setDescription] = useState(base.description);
  const [labels, setLabels] = useState<OutputLabel[]>(base.labels);
  const [questions, setQuestions] = useState<EditQuestion[]>(() => base.rubric.map(toEdit));
  const [saving, setSaving] = useState(false);
  const [drafting, setDrafting] = useState(false);

  const rubric = useMemo(() => questions.map(fromEdit), [questions]);
  const dirty = description !== base.description || JSON.stringify(labels) !== JSON.stringify(base.labels) || JSON.stringify(rubric) !== JSON.stringify(base.rubric);
  const invalidated = useMemo(() => new Set(invalidatedQuestions(base, { description, rubric })), [base, description, rubric]);
  const problem = editProblem(questions) ?? rubricProblem(outputType, outputType === "choice" ? labels : [], rubric);
  const labelsChanged = JSON.stringify(labels.map((l) => l.id)) !== JSON.stringify(base.labels.map((l) => l.id));

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save(next?: RubricQuestion[]) {
    setSaving(true);
    try {
      const body = { description, rubric: next ?? rubric, ...(outputType === "choice" ? { labels } : {}) };
      apply(await imEditDraft(id, body));
      toast.success(detail.draft ? `Saved to draft v${detail.draft.number}` : "Saved to a new draft");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  function applyProposal(proposed: RubricQuestion[], mode: "add" | "replace") {
    if (mode === "replace") return setQuestions(proposed.map(toEdit));
    const taken = questions.map((q) => q.id);
    const added = proposed.map((q) => {
      const id = taken.includes(q.id) ? uniqueSlug(q.id, taken) : q.id;
      taken.push(id);
      return toEdit({ ...q, id });
    });
    setQuestions([...questions, ...added].slice(0, 12));
  }

  async function addSuggested(q: RubricQuestion) {
    const fresh = toEdit({ ...q, id: uniqueSlug(q.id, questions.map((x) => x.id)) });
    if (dirty) {
      setQuestions([...questions, fresh]);
      toast("Added to your unsaved edits — save to apply");
      return;
    }
    await save([...rubric, fromEdit(fresh)]);
  }

  const suggestDisabled = !version?.metrics ? "Fit the head first so there are mistakes to learn from" : null;
  const examples = detail.counts.total;

  return (
    <div className="space-y-4 pb-16">
      {!detail.draft && detail.active && (
        <Callout tone="info">
          You’re viewing active v{detail.active.number}. Saving creates draft v{Math.max(...detail.versions.map((v) => v.number)) + 1}; the active version keeps serving until you promote it.
        </Callout>
      )}

      <Panel title="Description" description="What is being judged and what you care about. The judge reads this with every question, so changing it re-grades everything.">
        <textarea aria-label="Description" rows={5} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={6000} className={`${inputClass} resize-y leading-relaxed`} />
      </Panel>

      {outputType === "choice" && (
        <Panel title="Labels" description="The decisions this model outputs. Renaming or removing a label makes the head stale until you refit.">
          <LabelsEditor value={labels} onChange={setLabels} />
          {labelsChanged && <p className="m-0 mt-2 text-[11.5px] text-yellow-700 dark:text-yellow-400">Examples labeled with a removed id keep that label and won’t train until relabeled.</p>}
        </Panel>
      )}

      <Panel
        title={`Rubric questions · ${questions.length}`}
        description="Each question becomes one or more features the head weighs. Answers are cached per question, so only new or changed questions are re-asked."
        actions={
          questions.length > 0 ? (
            <Button variant="outline" size="sm" onClick={() => setDrafting(true)}>
              <Sparkles /> Draft with Claude
            </Button>
          ) : undefined
        }
      >
        {questions.length === 0 ? (
          <div className="py-6 text-center">
            <p className="m-0 text-[13.5px] font-medium text-foreground">No questions yet</p>
            <p className="mx-auto mt-1 max-w-md text-[12.5px] text-muted-foreground">
              Let Claude propose a starting rubric from your description and examples, then edit it. Or write questions yourself.
            </p>
            <div className="mt-3 flex justify-center gap-2">
              <Button variant="outline" onClick={() => setQuestions([newQuestion([])])}>
                Write one myself
              </Button>
              <Button onClick={() => setDrafting(true)}>
                <Sparkles /> Draft rubric with Claude
              </Button>
            </div>
          </div>
        ) : (
          <RubricEditor value={questions} onChange={setQuestions} invalidated={dirty ? invalidated : new Set()} />
        )}
      </Panel>

      <SuggestQuestion modelId={id} disabledReason={suggestDisabled} onAdd={addSuggested} />

      <DraftRubricDialog open={drafting} onOpenChange={setDrafting} modelId={id} hasQuestions={questions.length > 0} onApply={applyProposal} />

      {dirty && (
        <div className="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-popover px-4 py-2.5 shadow-md">
          <div className="min-w-0 flex-1 text-[12.5px]">
            {problem ? (
              <span className="text-red-600 dark:text-red-400">{problem}</span>
            ) : invalidated.size > 0 ? (
              <span className="text-dim">
                Unsaved changes. Saving re-grades {invalidated.size} question{invalidated.size === 1 ? "" : "s"} on {examples} example{examples === 1 ? "" : "s"} (the judge is called on Train → Grade).
              </span>
            ) : (
              <span className="text-dim">Unsaved changes. No cached answers are affected.</span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={saving}
            onClick={() => {
              setDescription(base.description);
              setLabels(base.labels);
              setQuestions(base.rubric.map(toEdit));
            }}
          >
            Discard
          </Button>
          <Button size="sm" disabled={saving || problem !== null} onClick={() => void save()}>
            {saving && <Spinner />}
            Save to draft
          </Button>
        </div>
      )}
    </div>
  );
}
