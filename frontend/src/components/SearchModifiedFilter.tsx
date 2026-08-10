"use client";

import { ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  modifiedRangeLabel,
  type ModifiedPreset,
  type ModifiedRange,
} from "@/app/search/modified-range";

const PRESETS: ModifiedPreset[] = ["any", "24h", "week", "month", "year"];

export default function SearchModifiedFilter({
  range,
  onChange,
}: {
  range: ModifiedRange;
  onChange: (range: ModifiedRange) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Last modified"
        className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-surface px-3 text-[12.5px] text-foreground hover:border-[var(--color-brand-300)]"
      >
        {modifiedRangeLabel(range)}
        <ChevronDown className="size-3.5 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56 text-[12.5px]">
        {PRESETS.map((preset) => (
          <DropdownMenuCheckboxItem
            key={preset}
            checked={range.preset === preset}
            onCheckedChange={() => onChange({ preset, from: "", to: "" })}
            // Keep the menu open — picking a range is often a two-step gesture.
            onSelect={(e) => e.preventDefault()}
          >
            {modifiedRangeLabel({ preset, from: "", to: "" })}
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        {/* Typing dates must not trigger Radix's menu typeahead. */}
        <div className="flex flex-col gap-2 px-2 py-1.5" onKeyDown={(e) => e.stopPropagation()}>
          <label className="flex flex-col gap-1 text-muted-foreground">
            From
            <input
              type="datetime-local"
              value={range.from}
              onChange={(e) => onChange({ preset: "custom", from: e.target.value, to: range.to })}
              className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 text-muted-foreground">
            To
            <input
              type="datetime-local"
              value={range.to}
              onChange={(e) => onChange({ preset: "custom", from: range.from, to: e.target.value })}
              className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
            />
          </label>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
