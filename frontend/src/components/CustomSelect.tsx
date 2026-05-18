"use client";

import { KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

export interface CustomSelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface CustomSelectProps {
  id?: string;
  value: string;
  options: CustomSelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
  menuClassName?: string;
  optionClassName?: string;
  align?: "left" | "right";
  autoFocus?: boolean;
}

const DEFAULT_TRIGGER_CLASS =
  "rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground";

export default function CustomSelect({
  id,
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  className = DEFAULT_TRIGGER_CLASS,
  menuClassName = "",
  optionClassName = "",
  align = "left",
  autoFocus = false,
}: CustomSelectProps) {
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const selectedIndex = useMemo(
    () => Math.max(0, options.findIndex((option) => option.value === value)),
    [options, value]
  );
  const selected = options[selectedIndex];

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (autoFocus) triggerRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    if (!open) return;

    const onMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  function openMenu() {
    setActiveIndex(selectedIndex);
    setOpen(true);
  }

  function selectOption(index: number) {
    const option = options[index];
    if (!option || option.disabled) return;

    onChange(option.value);
    setOpen(false);
  }

  function moveActive(direction: 1 | -1) {
    if (options.length === 0) return;

    let nextIndex = activeIndex;
    for (let count = 0; count < options.length; count += 1) {
      nextIndex = (nextIndex + direction + options.length) % options.length;
      if (!options[nextIndex]?.disabled) {
        setActiveIndex(nextIndex);
        return;
      }
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActive(1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActive(-1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      selectOption(activeIndex);
    }
  }

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button
        id={id}
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => {
          if (open) {
            setOpen(false);
            return;
          }
          openMenu();
        }}
        onKeyDown={onKeyDown}
        className={[
          "flex min-w-0 items-center justify-between gap-2 text-left outline-none",
          className,
          disabled ? "cursor-not-allowed opacity-50" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <span className="min-w-0 truncate">{selected?.label ?? "Select"}</span>
        <svg
          className={"h-3.5 w-3.5 shrink-0 transition-transform " + (open ? "rotate-180" : "")}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open ? (
        <div
          id={listboxId}
          role="listbox"
          className={[
            "absolute top-full z-[70] mt-1 max-h-64 min-w-full overflow-y-auto rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg",
            align === "right" ? "right-0" : "left-0",
            menuClassName,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {options.map((option, index) => {
            const selectedOption = option.value === value;
            const activeOption = index === activeIndex;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selectedOption}
                disabled={option.disabled}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectOption(index)}
                className={[
                  "flex w-full items-center gap-2 px-3 py-1.5 text-left text-foreground disabled:cursor-not-allowed disabled:opacity-50",
                  activeOption ? "bg-raised" : "hover:bg-raised",
                  optionClassName,
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="w-3 shrink-0 text-center">{selectedOption ? "✓" : ""}</span>
                <span className="min-w-0 truncate">{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
