"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";

interface Props {
  top: number;
  left: number;
  onCancel: () => void;
  onSubmit: (body: string) => Promise<void>;
}

// Small composer popover shown after the user clicks the inline "Comment"
// button. Used by both surfaces (markdown editor + iframe-rendered HTML)
// so the UX of starting a thread is identical regardless of page type.
export default function CommentComposerPopover({
  top,
  left,
  onCancel,
  onSubmit,
}: Props) {
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  async function submit() {
    const trimmed = body.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
    } finally {
      setSubmitting(false);
    }
  }

  function keepAnchorSelectionAlive(e: MouseEvent<HTMLDivElement>) {
    if (isTextControl(e.target)) return;
    e.preventDefault();
  }

  return (
    <div
      onMouseDown={keepAnchorSelectionAlive}
      className="absolute z-30 w-[260px] rounded-md border border-border-subtle bg-raised p-2 shadow-md"
      style={{ top, left }}
    >
      <textarea
        ref={textareaRef}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Add a comment…"
        disabled={submitting}
        rows={3}
        className="w-full resize-none rounded-sm border border-border-subtle bg-background p-2 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-600)]"
      />
      <div className="mt-1.5 flex justify-end gap-1.5">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="cursor-pointer rounded-sm px-2 py-1 text-[12px] text-muted-foreground hover:bg-background"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={submitting || !body.trim()}
          className="cursor-pointer rounded-sm bg-[var(--color-brand-600)] px-2.5 py-1 text-[12px] font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? "…" : "Comment"}
        </button>
      </div>
    </div>
  );
}

function isTextControl(target: EventTarget | null) {
  return target instanceof HTMLElement && !!target.closest("textarea, input");
}
