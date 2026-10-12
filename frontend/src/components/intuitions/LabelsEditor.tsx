"use client";

import { Flag, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { OutputLabel } from "@/lib/intuition-api";
import { isSlug, uniqueSlug } from "./im-helpers";
import { inputClass } from "./im-ui";

/** Edit the output labels of a choice model: slug id, what it means, and whether it flags a problem. */
export default function LabelsEditor({ value, onChange, disabled }: { value: OutputLabel[]; onChange: (labels: OutputLabel[]) => void; disabled?: boolean }) {
  const set = (index: number, patch: Partial<OutputLabel>) => onChange(value.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  return (
    <div className="space-y-1.5">
      {value.map((label, index) => {
        const bad = label.id !== "" && !isSlug(label.id);
        const dup = value.some((other, j) => j !== index && other.id === label.id && label.id !== "");
        return (
          <div key={index} className="grid grid-cols-[minmax(6rem,9rem)_minmax(0,1fr)_auto_auto] items-start gap-2">
            <input
              aria-label={`Label ${index + 1} id`}
              value={label.id}
              disabled={disabled}
              placeholder="send"
              onChange={(e) => set(index, { id: e.target.value.toLowerCase().replace(/\s+/g, "_") })}
              aria-invalid={bad || dup ? true : undefined}
              className={cn(inputClass, "py-1.5 font-mono text-[12px]", (bad || dup) && "border-red-500/60")}
            />
            <input
              aria-label={`Label ${index + 1} description`}
              value={label.description}
              disabled={disabled}
              placeholder="What this label means"
              onChange={(e) => set(index, { description: e.target.value })}
              className={cn(inputClass, "py-1.5")}
            />
            <button
              type="button"
              role="switch"
              aria-checked={!!label.flag}
              aria-label={`${label.id || `Label ${index + 1}`} needs fixing`}
              title={label.flag ? "Flagged: checks report this verdict as a finding. Click to unflag." : "Flag this label as “needs fixing” so checks report it as a finding"}
              disabled={disabled}
              onClick={() => set(index, { flag: !label.flag })}
              className={cn(
                "inline-flex h-[30px] items-center gap-1 rounded-md border px-2 text-[11.5px] whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50",
                label.flag
                  ? "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
                  : "border-border text-muted-foreground hover:border-red-500/30 hover:text-red-600",
              )}
            >
              <Flag className={cn("h-3 w-3", label.flag && "fill-current")} aria-hidden="true" />
              needs fixing
            </button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Remove label ${label.id || index + 1}`}
              disabled={disabled || value.length <= 2}
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              <X />
            </Button>
          </div>
        );
      })}
      <Button
        type="button"
        variant="outline"
        size="xs"
        disabled={disabled || value.length >= 12}
        onClick={() => onChange([...value, { id: uniqueSlug(`label_${value.length + 1}`, value.map((l) => l.id)), description: "" }])}
      >
        <Plus /> Add label
      </Button>
    </div>
  );
}
