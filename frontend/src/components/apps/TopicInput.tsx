"use client";

import { useMemo, useState } from "react";

/** A topic entry box that suggests labels already in use.

 *  Suggesting the existing vocabulary is the whole point: free typing is how
 *  a library ends up with "AI agents", "agentic AI" and "LLM agents" as three
 *  separate tags. The same reason the enrichment prompt is fed the vocabulary.
 */
export default function TopicInput({
  knownTopics,
  placeholder = "Add a topic…",
  onSubmit,
  onCancel,
}: {
  knownTopics: string[];
  placeholder?: string;
  onSubmit: (topic: string) => void;
  onCancel?: () => void;
}) {
  const [value, setValue] = useState("");

  const suggestions = useMemo(() => {
    const needle = value.trim().toLowerCase();
    if (!needle) return [];
    return knownTopics
      .filter((t) => t.toLowerCase().includes(needle) && t.toLowerCase() !== needle)
      .slice(0, 5);
  }, [value, knownTopics]);

  const commit = (topic: string) => {
    const clean = topic.trim();
    if (!clean) return;
    onSubmit(clean);
    setValue("");
  };

  return (
    <span className="relative inline-flex items-center gap-1.5">
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit(value);
          if (e.key === "Escape") onCancel?.();
        }}
        placeholder={placeholder}
        className="w-56 rounded-lg border border-border bg-base px-2.5 py-1.5 text-[12px] text-foreground placeholder:text-dim focus:border-brand focus:outline-none"
      />
      <button
        type="button"
        onClick={() => commit(value)}
        disabled={!value.trim()}
        className="cursor-pointer rounded-lg bg-brand px-2.5 py-1.5 text-[12px] font-medium text-white hover:bg-brand-hover disabled:opacity-40"
      >
        Add
      </button>
      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="cursor-pointer text-[12px] text-muted-foreground hover:text-foreground"
        >
          Cancel
        </button>
      )}

      {suggestions.length > 0 && (
        <span className="absolute left-0 top-full z-10 mt-1 flex w-56 flex-col overflow-hidden rounded-lg border border-border bg-base shadow-lg">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                commit(s);
              }}
              className="cursor-pointer px-2.5 py-1.5 text-left text-[12px] text-foreground hover:bg-raised"
            >
              {s}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}
