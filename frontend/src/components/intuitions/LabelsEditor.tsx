"use client";

import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { OutputLabel } from "@/lib/intuition-api";
import { isSlug, uniqueSlug } from "./im-helpers";
import { inputClass } from "./im-ui";

/** Edit the output labels of a choice model: slug id + what it means. */
export default function LabelsEditor({ value, onChange, disabled }: { value: OutputLabel[]; onChange: (labels: OutputLabel[]) => void; disabled?: boolean }) {
  const set = (index: number, patch: Partial<OutputLabel>) => onChange(value.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  return (
    <div className="space-y-1.5">
      {value.map((label, index) => {
        const bad = label.id !== "" && !isSlug(label.id);
        const dup = value.some((other, j) => j !== index && other.id === label.id && label.id !== "");
        return (
          <div key={index} className="grid grid-cols-[9rem_1fr_auto] items-start gap-2">
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
