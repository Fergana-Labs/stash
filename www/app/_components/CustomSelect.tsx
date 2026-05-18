"use client";

import { KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

export interface CustomSelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface CustomSelectProps {
  id?: string;
  name?: string;
  value: string;
  options: CustomSelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  className?: string;
  menuClassName?: string;
}

export default function CustomSelect({
  id,
  name,
  value,
  options,
  onChange,
  ariaLabel,
  className = "h-11 rounded-lg border border-border bg-surface px-3 text-[14px] text-ink outline-none transition focus:border-ink",
  menuClassName = "",
}: CustomSelectProps) {
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const selectedIndex = useMemo(
    () => Math.max(0, options.findIndex((option) => option.value === value)),
    [options, value]
  );
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return;

    const onMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
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

  function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
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
      {name ? <input type="hidden" name={name} value={value} /> : null}
      <button
        id={id}
        type="button"
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
        onKeyDown={onTriggerKeyDown}
        className={[
          "flex w-full min-w-0 items-center justify-between gap-2 text-left",
          className,
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
            "absolute left-0 top-full z-30 mt-1 max-h-64 min-w-full overflow-y-auto rounded-lg border border-border bg-background py-1 text-[14px] shadow-lg",
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
                  "flex w-full items-center gap-2 px-3 py-2 text-left text-ink disabled:cursor-not-allowed disabled:opacity-50",
                  activeOption ? "bg-surface" : "hover:bg-surface",
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
