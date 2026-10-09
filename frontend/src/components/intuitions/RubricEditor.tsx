"use client";

import { ArrowDown, ArrowUp, Plus, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { QuestionType, RubricQuestion } from "@/lib/intuition-api";
import { isSlug, MAX_QUESTIONS, questionOptions, uniqueSlug } from "./im-helpers";
import { inputClass } from "./im-ui";

/**
 * Editor-side question: keeps every type's criteria so switching type is lossless,
 * and keeps choice options as an ordered list so renaming a key never merges two options.
 */
export interface EditQuestion {
  uid: string;
  id: string;
  type: QuestionType;
  prompt: string;
  noul: { true: string; false: string };
  options: { key: string; text: string }[];
  levels: string[];
}

let counter = 0;
const uid = () => `q${++counter}`;

export function toEdit(q: RubricQuestion): EditQuestion {
  const base: EditQuestion = {
    uid: uid(),
    id: q.id,
    type: q.type,
    prompt: q.prompt,
    noul: { true: "", false: "" },
    options: [
      { key: "option_a", text: "" },
      { key: "option_b", text: "" },
    ],
    levels: ["Low", "Medium", "High"],
  };
  if (q.type === "noul" && !Array.isArray(q.criteria)) base.noul = { true: q.criteria.true ?? "", false: q.criteria.false ?? "" };
  if (q.type === "choice" && !Array.isArray(q.criteria)) base.options = Object.entries(q.criteria).map(([key, text]) => ({ key, text }));
  if (q.type === "score" && Array.isArray(q.criteria)) base.levels = [...q.criteria];
  return base;
}

export function fromEdit(q: EditQuestion): RubricQuestion {
  const criteria = q.type === "noul" ? { ...q.noul } : q.type === "choice" ? Object.fromEntries(q.options.map((o) => [o.key, o.text])) : [...q.levels];
  return { id: q.id, type: q.type, prompt: q.prompt, criteria };
}

export function newQuestion(taken: string[]): EditQuestion {
  return { ...toEdit({ id: uniqueSlug("new_question", taken), type: "noul", prompt: "", criteria: { true: "", false: "" } }) };
}

/** Problems the backend would reject that the converted rubric can't show (duplicate option keys). */
export function editProblem(questions: EditQuestion[]): string | null {
  for (const q of questions) {
    if (q.type !== "choice") continue;
    const keys = q.options.map((o) => o.key);
    if (new Set(keys).size !== keys.length) return `${q.id}: option names must be unique`;
  }
  return null;
}

const TYPE_OPTIONS = [
  { value: "noul", label: "Yes / no" },
  { value: "choice", label: "Choice" },
  { value: "score", label: "Score (ordered)" },
];

export default function RubricEditor({ value, onChange, invalidated }: { value: EditQuestion[]; onChange: (questions: EditQuestion[]) => void; invalidated: Set<string> }) {
  const set = (index: number, patch: Partial<EditQuestion>) => onChange(value.map((q, i) => (i === index ? { ...q, ...patch } : q)));
  const move = (index: number, by: number) => {
    const next = [...value];
    const [q] = next.splice(index, 1);
    next.splice(index + by, 0, q);
    onChange(next);
  };

  return (
    <div className="space-y-2.5">
      {value.map((q, index) => (
        <QuestionCard
          key={q.uid}
          q={q}
          index={index}
          count={value.length}
          duplicate={value.some((o, j) => j !== index && o.id === q.id)}
          changed={invalidated.has(q.id)}
          onChange={(patch) => set(index, patch)}
          onMove={(by) => move(index, by)}
          onRemove={() => onChange(value.filter((_, i) => i !== index))}
        />
      ))}
      <Button type="button" variant="outline" size="sm" disabled={value.length >= MAX_QUESTIONS} onClick={() => onChange([...value, newQuestion(value.map((q) => q.id))])}>
        <Plus /> Add question
      </Button>
      {value.length >= MAX_QUESTIONS && <span className="ml-2 text-[11.5px] text-muted-foreground">{MAX_QUESTIONS} questions is the maximum.</span>}
    </div>
  );
}

function QuestionCard({
  q,
  index,
  count,
  duplicate,
  changed,
  onChange,
  onMove,
  onRemove,
}: {
  q: EditQuestion;
  index: number;
  count: number;
  duplicate: boolean;
  changed: boolean;
  onChange: (patch: Partial<EditQuestion>) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const badId = !isSlug(q.id) || duplicate;
  return (
    <div className={cn("rounded-lg border bg-background", changed ? "border-brand-300/70" : "border-border")}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle px-3 py-2">
        <span className="w-5 text-right font-mono text-[11px] text-muted-foreground">{index + 1}</span>
        <input
          aria-label={`Question ${index + 1} id`}
          value={q.id}
          onChange={(e) => onChange({ id: e.target.value.toLowerCase().replace(/\s+/g, "_") })}
          aria-invalid={badId || undefined}
          title={duplicate ? "Ids must be unique" : !isSlug(q.id) ? "Lowercase letters, digits, _ or -" : "Question id; feature names start with it"}
          className={cn(inputClass, "h-7 w-48 py-0 font-mono text-[12px]", badId && "border-red-500/60")}
        />
        <Select aria-label={`Question ${index + 1} type`} value={q.type} onChange={(v) => onChange({ type: v as QuestionType })} options={TYPE_OPTIONS} className="h-7 w-36 px-2 text-[12px]" />
        {changed && <span className="tag tag-brand" title="Saving invalidates this question’s cached answers">will re-grade</span>}
        <span className="flex-1" />
        <Button type="button" size="icon-xs" variant="ghost" aria-label="Move up" disabled={index === 0} onClick={() => onMove(-1)}>
          <ArrowUp />
        </Button>
        <Button type="button" size="icon-xs" variant="ghost" aria-label="Move down" disabled={index === count - 1} onClick={() => onMove(1)}>
          <ArrowDown />
        </Button>
        <Button type="button" size="icon-xs" variant="ghost" aria-label={`Remove question ${q.id}`} onClick={onRemove}>
          <Trash2 />
        </Button>
      </div>
      <div className="space-y-2.5 px-3 py-2.5">
        <textarea
          aria-label={`Question ${index + 1} prompt`}
          rows={2}
          value={q.prompt}
          onChange={(e) => onChange({ prompt: e.target.value })}
          placeholder="Does the reply directly address the customer's actual question?"
          className={cn(inputClass, "resize-y", !q.prompt.trim() && "border-yellow-500/50")}
        />
        {q.type === "noul" && (
          <div className="grid gap-2 sm:grid-cols-2">
            {(["true", "false"] as const).map((k) => (
              <label key={k} className="block">
                <span className="mb-1 block text-[11px] font-medium text-dim">{k === "true" ? "Yes means" : "No means"}</span>
                <input value={q.noul[k]} onChange={(e) => onChange({ noul: { ...q.noul, [k]: e.target.value } })} className={cn(inputClass, "py-1.5 text-[12.5px]")} />
              </label>
            ))}
          </div>
        )}
        {q.type === "choice" && <ChoiceOptions q={q} onChange={onChange} />}
        {q.type === "score" && <ScoreLevels q={q} onChange={onChange} />}
      </div>
    </div>
  );
}

function ChoiceOptions({ q, onChange }: { q: EditQuestion; onChange: (patch: Partial<EditQuestion>) => void }) {
  const set = (i: number, patch: Partial<{ key: string; text: string }>) => onChange({ options: q.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  return (
    <div className="space-y-1.5">
      <span className="block text-[11px] font-medium text-dim">Options</span>
      {q.options.map((o, i) => {
        const dup = q.options.some((p, j) => j !== i && p.key === o.key);
        return (
          <div key={i} className="grid grid-cols-[9rem_1fr_auto] gap-2">
            <input aria-label={`Option ${i + 1} name`} value={o.key} onChange={(e) => set(i, { key: e.target.value })} className={cn(inputClass, "py-1.5 font-mono text-[12px]", (dup || !o.key.trim()) && "border-red-500/60")} />
            <input aria-label={`Option ${i + 1} description`} value={o.text} onChange={(e) => set(i, { text: e.target.value })} placeholder="What this option means" className={cn(inputClass, "py-1.5 text-[12.5px]")} />
            <Button type="button" size="icon-sm" variant="ghost" aria-label={`Remove option ${o.key}`} disabled={q.options.length <= 2} onClick={() => onChange({ options: q.options.filter((_, j) => j !== i) })}>
              <X />
            </Button>
          </div>
        );
      })}
      <Button
        type="button"
        size="xs"
        variant="outline"
        disabled={q.options.length >= 12}
        onClick={() => onChange({ options: [...q.options, { key: uniqueSlug(`option_${q.options.length + 1}`, q.options.map((o) => o.key)), text: "" }] })}
      >
        <Plus /> Option
      </Button>
    </div>
  );
}

function ScoreLevels({ q, onChange }: { q: EditQuestion; onChange: (patch: Partial<EditQuestion>) => void }) {
  const move = (i: number, by: number) => {
    const next = [...q.levels];
    const [level] = next.splice(i, 1);
    next.splice(i + by, 0, level);
    onChange({ levels: next });
  };
  return (
    <div className="space-y-1.5">
      <span className="block text-[11px] font-medium text-dim">Levels, lowest first</span>
      {q.levels.map((text, i) => (
        <div key={i} className="grid grid-cols-[1.5rem_1fr_auto] items-center gap-2">
          <span className="text-right font-mono text-[11px] text-muted-foreground">{i}</span>
          <input aria-label={`Level ${i}`} value={text} onChange={(e) => onChange({ levels: q.levels.map((l, j) => (j === i ? e.target.value : l)) })} className={cn(inputClass, "py-1.5 text-[12.5px]")} />
          <div className="flex">
            <Button type="button" size="icon-xs" variant="ghost" aria-label={`Move level ${i} up`} disabled={i === 0} onClick={() => move(i, -1)}>
              <ArrowUp />
            </Button>
            <Button type="button" size="icon-xs" variant="ghost" aria-label={`Move level ${i} down`} disabled={i === q.levels.length - 1} onClick={() => move(i, 1)}>
              <ArrowDown />
            </Button>
            <Button type="button" size="icon-xs" variant="ghost" aria-label={`Remove level ${i}`} disabled={q.levels.length <= 2} onClick={() => onChange({ levels: q.levels.filter((_, j) => j !== i) })}>
              <X />
            </Button>
          </div>
        </div>
      ))}
      <Button type="button" size="xs" variant="outline" disabled={q.levels.length >= 10} onClick={() => onChange({ levels: [...q.levels, ""] })}>
        <Plus /> Level
      </Button>
    </div>
  );
}

/** Read-only rendering of a question (proposals, version snapshots). */
export function QuestionPreview({ q, className }: { q: RubricQuestion; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-foreground">{q.prompt}</span>
        <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
          {q.id} · {q.type === "noul" ? "yes/no" : q.type}
        </span>
      </div>
      <ul className="m-0 mt-1 list-none space-y-0.5 p-0 text-[11.5px] text-muted-foreground">
        {questionOptions(q).map((o) => (
          <li key={o.key} className="truncate" title={o.label}>
            {q.type === "noul" ? (
              <>
                <span className="font-mono">{o.label}</span> — {(q.criteria as Record<string, string>)[o.key] || "—"}
              </>
            ) : q.type === "score" ? (
              <>
                <span className="font-mono">{o.key}</span> {o.label}
              </>
            ) : (
              o.label
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
