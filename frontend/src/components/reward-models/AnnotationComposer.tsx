"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { RmQuote } from "@/lib/types";

export interface ComposerTarget {
  stepId: string | null;
  quote: RmQuote | null;
  /** Position inside the trace canvas, in px. */
  top: number;
  left: number;
}

export const COMPOSER_WIDTH = 320;

/** Google-Docs-style popover for a new annotation: a comment plus an optional + / −. */
export default function AnnotationComposer({
  target,
  label,
  allowRating,
  onCancel,
  onSubmit,
}: {
  target: ComposerTarget;
  label: string;
  /** False on system steps, which the server refuses to rate. */
  allowRating: boolean;
  onCancel: () => void;
  onSubmit: (comment: string, rating: 1 | -1 | null) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const empty = comment.trim() === "" && rating === null;

  useEffect(() => {
    textarea.current?.focus();
  }, []);

  // Clicking away discards an untouched composer, like Google Docs. A draft
  // with text stays open so a stray click can't lose it.
  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (root.current?.contains(e.target as Node)) return;
      if (empty) onCancel();
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [empty, onCancel]);

  async function submit() {
    if (empty) return;
    setSubmitting(true);
    try {
      await onSubmit(comment.trim(), rating);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      ref={root}
      className="absolute z-30 rounded-lg border border-border bg-popover p-2.5 shadow-lg ring-1 ring-foreground/5 animate-in fade-in-0 zoom-in-95"
      style={{ top: target.top, left: target.left, width: COMPOSER_WIDTH }}
    >
      <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">{label}</div>
      {target.quote && (
        <div className="mb-2 line-clamp-2 border-l-2 border-amber-400 pl-2 text-[12px] leading-snug text-dim italic">
          {target.quote.text}
        </div>
      )}
      <textarea
        ref={textarea}
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
      <div className="mt-2 flex items-center gap-1.5">
        {allowRating && (
          <>
            <RatingChoice value={1} selected={rating === 1} onClick={() => setRating(rating === 1 ? null : 1)} />
            <RatingChoice value={-1} selected={rating === -1} onClick={() => setRating(rating === -1 ? null : -1)} />
          </>
        )}
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => void submit()} disabled={empty || submitting}>
          {submitting && <Loader2 className="animate-spin" />}
          Comment
        </Button>
      </div>
    </div>
  );
}

function RatingChoice({ value, selected, onClick }: { value: 1 | -1; selected: boolean; onClick: () => void }) {
  const positive = value === 1;
  const Icon = positive ? Plus : Minus;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      title={positive ? "Mark as good (+)" : "Mark as bad (−)"}
      className={cn(
        "inline-flex size-7 cursor-pointer items-center justify-center rounded-md border transition-colors",
        selected
          ? positive
            ? "border-green-600/40 bg-green-600/12 text-green-700 dark:text-green-400"
            : "border-red-500/40 bg-red-500/12 text-red-600 dark:text-red-400"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} />
    </button>
  );
}
