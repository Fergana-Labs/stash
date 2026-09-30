"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { RmQuote } from "@/lib/types";

export interface ComposerTarget {
  stepId: string | null;
  quote: RmQuote | null;
}

export default function AnnotationComposer({
  target,
  label,
  onCancel,
  onSubmit,
}: {
  target: ComposerTarget;
  label: string;
  onCancel: () => void;
  onSubmit: (comment: string) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
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
      await onSubmit(comment.trim());
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div ref={root}>
      <div className="mb-1.5 text-[11px] font-medium text-muted-foreground">{label}</div>
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
      <div className="mt-2 flex items-center gap-1.5">
        <span className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => void submit()} disabled={empty || submitting}>
          {submitting ? "Saving…" : "Comment"}
        </Button>
      </div>
    </div>
  );
}
