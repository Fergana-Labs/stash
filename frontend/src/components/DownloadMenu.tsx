"use client";

import { useEffect, useRef, useState } from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

export interface DownloadOption {
  label: string;
  onSelect: () => void;
  // Destructive options render below a divider in red so a misplaced
  // click on "Delete" doesn't land inside the routine download formats.
  destructive?: boolean;
}

export default function DownloadMenu({ options }: { options: DownloadOption[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  const safe = options.filter((o) => !o.destructive);
  const destructive = options.filter((o) => o.destructive);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="rounded-md border border-border bg-base px-2.5 py-1 text-[12px] text-muted hover:bg-raised hover:text-foreground"
      >
        Download ▾
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-md border border-border bg-surface py-1 text-[12.5px] shadow-lg">
          {safe.map((o) => (
            <button
              key={o.label}
              onClick={() => {
                setOpen(false);
                o.onSelect();
              }}
              className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised"
            >
              {o.label}
            </button>
          ))}
          {destructive.length > 0 && safe.length > 0 && (
            <div className="my-1 border-t border-border" />
          )}
          {destructive.map((o) => (
            <button
              key={o.label}
              onClick={() => {
                setOpen(false);
                o.onSelect();
              }}
              className="block w-full px-3 py-1.5 text-left text-red-600 hover:bg-red-500/10"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function downloadBlob(content: string, mimeType: string, filename: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
