"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";
import type { Item } from "@/lib/intuition-api";
import { fieldText, isEmptyItem, parseItemJson } from "./im-helpers";
import { inputClass } from "./im-ui";

/** Editable item state. `keys` (from detectItemKeys) decides between per-field and single-text editing. */
export interface ItemDraft {
  raw: boolean;
  fields: Record<string, string>;
  text: string;
  json: string;
}

export function emptyDraft(): ItemDraft {
  return { raw: false, fields: {}, text: "", json: "" };
}

export function draftFromItem(item: Item, keys: string[] | null): ItemDraft {
  if (typeof item === "string") return keys ? { raw: true, fields: {}, text: item, json: JSON.stringify(item) } : { ...emptyDraft(), text: item };
  if (keys && Object.keys(item).every((k) => keys.includes(k))) return { ...emptyDraft(), fields: Object.fromEntries(keys.map((k) => [k, fieldText(item[k])])) };
  return { raw: true, fields: {}, text: "", json: JSON.stringify(item, null, 2) };
}

/** Build the item, or explain why it can't be built. */
export function draftToItem(draft: ItemDraft, keys: string[] | null): { item: Item } | { error: string } {
  let result: { item: Item } | { error: string };
  if (draft.raw) result = parseItemJson(draft.json);
  else if (keys) result = { item: Object.fromEntries(keys.map((k) => [k, draft.fields[k] ?? ""])) };
  else result = { item: draft.text };
  if ("item" in result && isEmptyItem(result.item)) return { error: "Item is empty" };
  return result;
}

function toRaw(draft: ItemDraft, keys: string[] | null): string {
  const built = draftToItem({ ...draft, raw: false }, keys);
  if ("item" in built) return JSON.stringify(built.item, null, 2);
  return keys ? JSON.stringify(Object.fromEntries(keys.map((k) => [k, ""])), null, 2) : '""';
}

function fromRaw(draft: ItemDraft, keys: string[] | null): ItemDraft {
  const parsed = parseItemJson(draft.json);
  // Stay in raw mode when the JSON is invalid or doesn't fit the field editor.
  if ("error" in parsed) return draft;
  const next = draftFromItem(parsed.item, keys);
  return next.raw ? draft : next;
}

/**
 * Item editor: one textarea per field when the model's items share a shape,
 * otherwise a single textarea; "Raw JSON" switches to a JSON textarea.
 */
export default function ItemInput({
  keys,
  value,
  onChange,
  label,
  rows = 3,
  disabled,
  onSubmit,
}: {
  keys: string[] | null;
  value: ItemDraft;
  onChange: (draft: ItemDraft) => void;
  label?: string;
  rows?: number;
  disabled?: boolean;
  /** Cmd/Ctrl+Enter inside any textarea. */
  onSubmit?: () => void;
}) {
  const id = useId();
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (onSubmit && e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      onSubmit();
    }
  };
  const area = cn(inputClass, "resize-y leading-relaxed");
  const rawError = value.raw && value.json.trim() ? (() => { const p = parseItemJson(value.json); return "error" in p ? p.error : null; })() : null;

  return (
    <fieldset disabled={disabled} aria-label={label ?? "Item"} className="min-w-0 space-y-2">
      <div className="flex items-center justify-between gap-2">
        {label ? <span className="text-[12px] font-medium text-dim">{label}</span> : <span />}
        <label className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
          <input
            type="checkbox"
            checked={value.raw}
            onChange={(e) => onChange(e.target.checked ? { ...value, raw: true, json: toRaw(value, keys) } : fromRaw(value, keys))}
            className="accent-brand-500"
          />
          Raw JSON
        </label>
      </div>
      {value.raw ? (
        <>
          <textarea
            aria-label={label ? `${label} JSON` : "Item JSON"}
            rows={Math.max(rows + 1, 4)}
            value={value.json}
            onChange={(e) => onChange({ ...value, json: e.target.value })}
            onKeyDown={onKeyDown}
            spellCheck={false}
            className={cn(area, "font-mono text-[12px]")}
            aria-invalid={rawError ? true : undefined}
          />
          {rawError && <p className="m-0 text-[11.5px] text-red-600 dark:text-red-400">{rawError}</p>}
        </>
      ) : keys ? (
        keys.map((k) => (
          <div key={k}>
            <label htmlFor={`${id}-${k}`} className="mb-1 block text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">
              {k}
            </label>
            <textarea
              id={`${id}-${k}`}
              rows={rows}
              value={value.fields[k] ?? ""}
              onChange={(e) => onChange({ ...value, fields: { ...value.fields, [k]: e.target.value } })}
              onKeyDown={onKeyDown}
              className={area}
            />
          </div>
        ))
      ) : (
        <textarea
          aria-label={label ?? "Item"}
          rows={rows + 1}
          value={value.text}
          onChange={(e) => onChange({ ...value, text: e.target.value })}
          onKeyDown={onKeyDown}
          placeholder="The text to judge"
          className={area}
        />
      )}
    </fieldset>
  );
}
