"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface Props {
  /** Current value, controlled from outside. */
  value: string;
  /**
   * Called when the user commits a new value (Enter or blur). Resolve the
   * promise with the canonical name to display after save; reject (or
   * throw) to surface an error and revert.
   */
  onSave: (next: string) => Promise<string | void>;
  /** Optional: locks editing entirely (read-only views). */
  disabled?: boolean;
  /** CSS class applied to the rendered text/input. */
  className?: string;
  /** Placeholder shown when the input is empty. */
  placeholder?: string;
  /** Optional title attribute on the static span. */
  title?: string;
}

// Inline-edit-on-click pattern used by the page header, file viewer header,
// and the file-browser folder strip. Commits on Enter or blur, reverts on
// Escape, and trims whitespace before save. Empty saves are rejected
// silently (revert to the previous value).
export default function EditableTitle({
  value,
  onSave,
  disabled,
  className,
  placeholder,
  title,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // External value changed while we're not editing → reflect it.
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  async function commit() {
    const next = draft.trim();
    if (!next || next === value) {
      setDraft(value);
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const result = await onSave(next);
      setDraft(typeof result === "string" ? result : next);
      setEditing(false);
    } catch {
      // On error, revert to the original. The caller is responsible for
      // surfacing the error to the user (toast / banner) — this component
      // just owns the inline edit lifecycle.
      setDraft(value);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setDraft(value);
      setEditing(false);
    }
  }

  if (disabled || !editing) {
    return (
      <span
        className={
          (className ?? "") +
          (disabled
            ? ""
            : " cursor-text rounded px-1 py-0.5 -mx-1 hover:bg-raised")
        }
        title={disabled ? title : title ?? "Click to rename"}
        onClick={() => {
          if (!disabled) setEditing(true);
        }}
      >
        {value}
      </span>
    );
  }

  return (
    <input
      ref={inputRef}
      value={draft}
      // Grow the input with its content so long titles aren't clipped. `size`
      // is in characters; it auto-widens as the user types and shrinks back.
      size={Math.max(draft.length, placeholder?.length ?? 1, 1)}
      disabled={saving}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={onKey}
      onBlur={commit}
      placeholder={placeholder}
      className={
        (className ?? "") +
        " max-w-full rounded border border-[var(--color-brand-300)] bg-base px-1 py-0.5 -mx-1 outline-none focus:border-[var(--color-brand-500)]"
      }
    />
  );
}
