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
  searchable?: boolean;
  searchPlaceholder?: string;
}

const DEFAULT_TRIGGER_CLASS =
  "rounded-md border border-border bg-surface px-2 py-1.5 text-[12px] text-foreground";

function firstEnabledIndex(options: CustomSelectOption[]) {
  return Math.max(0, options.findIndex((option) => !option.disabled));
}

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
  searchable = false,
  searchPlaceholder = "Search…",
}: CustomSelectProps) {
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [query, setQuery] = useState("");

  const selected = useMemo(
    () => options.find((option) => option.value === value),
    [options, value]
  );

  // The menu lists only options matching the search query; activeIndex and
  // keyboard navigation operate over this filtered view.
  const visibleOptions = useMemo(() => {
    if (!searchable) return options;
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return options;
    return options.filter((option) => option.label.toLowerCase().includes(trimmed));
  }, [searchable, options, query]);

  function openMenu() {
    setQuery("");
    const selectedIndex = options.findIndex((option) => option.value === value);
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : firstEnabledIndex(options));
    setOpen(true);
  }

  function closeMenu() {
    setOpen(false);
    setQuery("");
  }

  // Narrowing the query re-highlights the first remaining match.
  function changeQuery(next: string) {
    setQuery(next);
    const trimmed = next.trim().toLowerCase();
    const matches = trimmed
      ? options.filter((option) => option.label.toLowerCase().includes(trimmed))
      : options;
    setActiveIndex(firstEnabledIndex(matches));
  }

  useEscapeKey(open, closeMenu);

  useEffect(() => {
    if (autoFocus) triggerRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    if (open && searchable) searchRef.current?.focus();
  }, [open, searchable]);

  useEffect(() => {
    if (!open) return;

    const onMouseDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    };
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  function selectOption(index: number) {
    const option = visibleOptions[index];
    if (!option || option.disabled) return;

    onChange(option.value);
    closeMenu();
  }

  function moveActive(direction: 1 | -1) {
    if (visibleOptions.length === 0) return;

    let nextIndex = activeIndex;
    for (let count = 0; count < visibleOptions.length; count += 1) {
      nextIndex = (nextIndex + direction + visibleOptions.length) % visibleOptions.length;
      if (!visibleOptions[nextIndex]?.disabled) {
        setActiveIndex(nextIndex);
        return;
      }
    }
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLElement>) {
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

    // Space inserts a character while searching, so only the trigger treats it
    // as an open/select shortcut.
    const isSelectKey = event.key === "Enter" || (event.key === " " && !searchable);
    if (isSelectKey) {
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
            closeMenu();
            return;
          }
          openMenu();
        }}
        onKeyDown={onMenuKeyDown}
        className={[
          "flex min-w-0 items-center justify-between gap-2 text-left outline-none",
          className,
          disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
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
          className={[
            "absolute top-full z-[70] mt-1 min-w-full rounded-md border border-border bg-surface text-[12.5px] shadow-lg",
            align === "right" ? "right-0" : "left-0",
            menuClassName,
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {searchable ? (
            <div className="border-b border-border p-1.5">
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(event) => changeQuery(event.target.value)}
                onKeyDown={onMenuKeyDown}
                placeholder={searchPlaceholder}
                aria-label={ariaLabel ? `Search ${ariaLabel}` : "Search options"}
                className="w-full rounded border border-border bg-base px-2 py-1 text-[12.5px] text-foreground outline-none focus:border-brand"
              />
            </div>
          ) : null}

          <div id={listboxId} role="listbox" className="max-h-64 overflow-y-auto py-1">
            {visibleOptions.length === 0 ? (
              <div className="px-3 py-1.5 text-muted-foreground">No matches</div>
            ) : (
              visibleOptions.map((option, index) => {
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
                      "flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-foreground disabled:cursor-not-allowed disabled:opacity-50",
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
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
