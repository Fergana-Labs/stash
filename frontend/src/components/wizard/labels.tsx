"use client";

import { useEffect } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ModelDetail, OutputType } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";

/** What an item can be labeled: one label (choice / preference) or any set of issues (multi). */
export interface LabelSpace { kind: OutputType; options: { id: string; description: string }[] }
export const NO_ISSUES = "none";

export const PAIR_SPACE: LabelSpace = { kind: "choice", options: [{ id: "a", description: "A is better" }, { id: "b", description: "B is better" }] };

export function labelSpace(detail: Pick<ModelDetail, "model" | "draft" | "active">, pair = false): LabelSpace {
  if (pair) return PAIR_SPACE;
  const version = detail.draft ?? detail.active;
  if (detail.model.output_type === "preference") return { kind: "preference", options: [{ id: "good", description: "A good output" }, { id: "bad", description: "A poor output" }] };
  return { kind: detail.model.output_type, options: (version?.labels ?? []).map((l) => ({ id: l.id, description: l.description })) };
}

export const issuesOf = (label: string | null | undefined) => (!label || label === NO_ISSUES ? [] : label.split("+"));
export const issuesLabel = (issues: string[]) => [...issues].sort().join("+") || NO_ISSUES;

/** A label as people read it: multi-issue sets become "a, b" or "No issues". */
export function showLabel(label: string | null | undefined, kind?: OutputType): string {
  if (label == null) return "—";
  if (kind === "multi" || label.includes("+") || label === NO_ISSUES) return label === NO_ISSUES ? "No issues" : issuesOf(label).join(", ");
  return label;
}

export function LabelChip({ label, kind, tone }: { label: string | null | undefined; kind?: OutputType; tone?: "judge" | "you" | "muted" }) {
  return <span className={cn("inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px]", tone === "judge" ? "border-border bg-raised" : tone === "you" ? "border-brand-500/40 bg-brand-500/10" : "border-border text-muted-foreground")}>{showLabel(label, kind)}</span>;
}

/**
 * Pick a label. Choice and preference: a click (or number key) commits. Multi:
 * number keys toggle issues, 0 means no issues, Enter commits.
 */
export function LabelPicker({ space, value, onPick, suggested, keyboard = true, disabled = false, commitLabel = "Save" }: {
  space: LabelSpace; value: string | null; onPick: (label: string, commit: boolean) => void;
  suggested?: string | null; keyboard?: boolean; disabled?: boolean; commitLabel?: string;
}) {
  const multi = space.kind === "multi";
  const chosen = new Set(issuesOf(value));

  useEffect(() => {
    if (!keyboard || disabled) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /input|textarea|select/i.test(target.tagName)) return;
      const n = Number(e.key);
      if (multi) {
        if (e.key === "0") { e.preventDefault(); onPick(NO_ISSUES, false); }
        else if (n >= 1 && n <= space.options.length) {
          e.preventDefault();
          const id = space.options[n - 1].id;
          const next = new Set(chosen); if (next.has(id)) next.delete(id); else next.add(id);
          onPick(issuesLabel([...next]), false);
        } else if (e.key === "Enter" && value != null) { e.preventDefault(); onPick(value, true); }
      } else if (n >= 1 && n <= space.options.length) { e.preventDefault(); onPick(space.options[n - 1].id, true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {space.options.map((o, i) => {
        const on = multi ? chosen.has(o.id) : value === o.id;
        const hint = multi ? issuesOf(suggested).includes(o.id) : suggested === o.id;
        return (
          <Button key={o.id} size="sm" variant={on ? "default" : "outline"} disabled={disabled} title={o.description} aria-pressed={on}
            className={cn(hint && !on && "border-brand-500/60")}
            onClick={() => {
              if (!multi) return onPick(o.id, true);
              const next = new Set(chosen); if (next.has(o.id)) next.delete(o.id); else next.add(o.id);
              onPick(issuesLabel([...next]), false);
            }}>
            {keyboard && <kbd className="mr-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">{i + 1}</kbd>}
            {multi && on && <Check className="size-3" />}{o.id}{hint && !on && <span className="ml-1 text-[10px] text-brand-600 dark:text-brand-400">suggested</span>}
          </Button>
        );
      })}
      {multi && (
        <>
          <Button size="sm" variant={value === NO_ISSUES ? "default" : "outline"} disabled={disabled} aria-pressed={value === NO_ISSUES} onClick={() => onPick(NO_ISSUES, false)}>
            {keyboard && <kbd className="mr-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">0</kbd>}No issues
          </Button>
          <Button size="sm" disabled={disabled || value == null} onClick={() => value != null && onPick(value, true)}>{commitLabel}{keyboard && <kbd className="ml-1 rounded border border-current/30 px-1 font-mono text-[10px] opacity-70">↵</kbd>}</Button>
        </>
      )}
    </div>
  );
}
