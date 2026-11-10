"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { RmQuote } from "@/lib/types";

export interface ComposerTarget {
  stepId: string | null;
  quote: RmQuote | null;
}

/** Adding the commented step to an eval as an example: which eval, and whether it is a good or
 * a bad one. */
export interface AddToEval {
  evalId: string;
  label: "good" | "bad";
}

export default function AnnotationComposer({
  target,
  label,
  evals = [],
  onCancel,
  onSubmit,
}: {
  target: ComposerTarget;
  label: string;
  /** The evals a comment on a step can also add that step to, as an example. */
  evals?: { id: string; name: string }[];
  onCancel: () => void;
  onSubmit: (comment: string, add: AddToEval | null) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [evalId, setEvalId] = useState("");
  const [verdict, setVerdict] = useState<AddToEval["label"]>("bad");
  const canAdd = evals.length > 0 && target.stepId !== null;
  const [submitting, setSubmitting] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const empty = comment.trim() === "";

  useEffect(() => {
    root.current?.scrollIntoView({ block: "nearest" });
    textarea.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!empty) return;
    function onPointerDown(event: PointerEvent) {
      if (root.current?.contains(event.target as Node)) return;
      onCancel();
    }
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [empty, onCancel]);

  async function submit() {
    if (empty) return;
    setSubmitting(true);
    try {
      await onSubmit(comment.trim(), canAdd && evalId ? { evalId, label: verdict } : null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div ref={root}>
      {target.quote && (
        <div className="mb-2 line-clamp-2 border-l-2 border-amber-400 pl-2 text-[12px] leading-snug text-dim italic">
          {target.quote.text}
        </div>
      )}
      <textarea
        ref={textarea}
        aria-label={label}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
        placeholder="What's good or wrong here?"
        rows={3}
        className="w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-[13px] leading-snug text-foreground outline-none placeholder:text-muted-foreground focus:border-brand-400 focus:ring-2 focus:ring-brand-400/20"
      />
      {canAdd && (
        <div className="mt-2 flex items-center gap-1.5 text-[12px]">
          <select
            aria-label="Add to eval"
            value={evalId}
            onChange={(e) => setEvalId(e.target.value)}
            className="h-7 min-w-0 flex-1 rounded border border-border bg-background px-1.5 text-[12px] text-foreground outline-none focus:border-brand-400"
          >
            <option value="">Add to eval</option>
            {evals.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          {evalId && (
            <div role="group" aria-label="Example label" className="flex shrink-0 rounded border border-border p-px">
              {(["bad", "good"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={verdict === v}
                  onClick={() => setVerdict(v)}
                  className={`h-6 rounded-sm px-2 ${verdict === v ? "bg-surface font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  {v === "bad" ? "Bad" : "Good"}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="mt-2 flex items-center gap-1.5">
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => void submit()} disabled={empty || submitting}>
          {submitting ? "Saving…" : canAdd && evalId ? "Comment and add" : "Comment"}
        </Button>
      </div>
    </div>
  );
}
