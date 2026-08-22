"use client";

import * as React from "react";
import { Select as SelectPrimitive } from "radix-ui";
import { CheckIcon, ChevronDownIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

// Radix rejects items whose value is the empty string, but several callers use
// "" to mean "no filter" / "unset". Map it through a sentinel at this boundary
// so call sites keep their natural values.
const EMPTY = "__empty__";

export function Select({
  value,
  onChange,
  options,
  disabled,
  id,
  "aria-label": ariaLabel,
  className,
  portal = true,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  className?: string;
  // Render the options in place instead of portaling to <body>. Required
  // inside containers that close on document-level outside clicks (e.g. the
  // share popover), where a portaled option click reads as "outside".
  portal?: boolean;
}) {
  return (
    <SelectPrimitive.Root
      value={value === "" ? EMPTY : value}
      onValueChange={(v) => onChange(v === EMPTY ? "" : v)}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "flex cursor-pointer items-center justify-between gap-2 rounded-md border border-border bg-base text-left text-foreground focus:outline-none focus-visible:border-brand-500 focus-visible:ring-2 focus-visible:ring-brand-500/20 disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
      >
        <span className="truncate">
          <SelectPrimitive.Value />
        </span>
        <SelectPrimitive.Icon>
          <ChevronDownIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <MaybePortal portal={portal}>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-(--radix-select-content-available-height) min-w-(--radix-select-trigger-width) overflow-y-auto rounded-lg bg-popover p-1 text-popover-foreground shadow-md ring-1 ring-foreground/10 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95"
        >
          <SelectPrimitive.Viewport>
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value === "" ? EMPTY : option.value}
                className="relative flex cursor-default items-center gap-1.5 rounded-md py-1.5 pr-2 pl-7 text-[13px] outline-none select-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
              >
                <span className="absolute left-1.5 flex w-4 justify-center">
                  <SelectPrimitive.ItemIndicator>
                    <CheckIcon className="h-3.5 w-3.5" />
                  </SelectPrimitive.ItemIndicator>
                </span>
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </MaybePortal>
    </SelectPrimitive.Root>
  );
}

function MaybePortal({ portal, children }: { portal: boolean; children: React.ReactNode }) {
  if (!portal) return <>{children}</>;
  return <SelectPrimitive.Portal>{children}</SelectPrimitive.Portal>;
}
