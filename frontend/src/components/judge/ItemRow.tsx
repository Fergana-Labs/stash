"use client";

import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import ItemView from "@/components/intuitions/ItemView";
import type { Item } from "@/lib/intuition-api";
import { cn } from "@/lib/utils";

/**
 * One input in a list -- the Inbox (raw traffic) and the Golden set (labeled data)
 * share this row so they read the same: the input on the left, the decision on
 * the right, and the editor underneath when it is open.
 */
export function ItemRow({ item, itemB, badges, decision, open, onToggle, children }: {
  item: Item; itemB?: Item | null; badges?: ReactNode; decision: ReactNode; open: boolean; onToggle: () => void; children?: ReactNode;
}) {
  return (
    <li className={cn("rounded border bg-background transition-colors", open ? "border-foreground/25" : "border-border hover:border-foreground/20")}>
      <div role="button" tabIndex={0} aria-expanded={open} onClick={onToggle} onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onToggle(); }} className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
        <div className="min-w-0 flex-1">
          {itemB ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">A</div><ItemView item={item} clamp={!open} /></div>
              <div><div className="mb-1 text-[10.5px] font-semibold text-muted-foreground">B</div><ItemView item={itemB} clamp={!open} /></div>
            </div>
          ) : <div className={cn(!open && "max-h-36 overflow-hidden [&_img]:max-h-28")}><ItemView item={item} clamp={!open} /></div>}
          {badges && <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">{badges}</div>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-right">{decision}</div>
        <ChevronDown className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </div>
      {open && children && <div className="border-t border-border bg-surface/30 px-3.5 py-3" onClick={(e) => e.stopPropagation()}>{children}</div>}
    </li>
  );
}

export function Badge({ children, tone }: { children: ReactNode; tone?: "brand" | "warn" }) {
  return <span className={cn("rounded px-1.5 py-px text-[10.5px]", tone === "brand" ? "bg-brand-500/12 text-brand-700 dark:text-brand-300" : tone === "warn" ? "bg-amber-500/12 text-amber-800 dark:text-amber-300" : "bg-raised")}>{children}</span>;
}

export function FilterChips<T extends string>({ value, options, onChange }: { value: T; options: { id: T; label: string; count?: number; title?: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button key={o.id} role="tab" type="button" aria-selected={value === o.id} title={o.title} onClick={() => onChange(o.id)} className={cn("rounded border px-2.5 py-1 text-[12px]", value === o.id ? "border-foreground bg-foreground text-background" : "border-border text-muted-foreground hover:text-foreground")}>
          {o.label}{o.count != null && <span className="ml-1 tabular-nums opacity-70">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
