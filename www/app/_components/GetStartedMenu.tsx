"use client";

import { useEffect, useRef, useState } from "react";

// The hero's single CTA. "Developer" carries next=/developer so the app sends
// the new account straight into the Developer Platform instead of personal
// onboarding; "Personal" is the plain signup.
export default function GetStartedMenu({ appUrl }: { appUrl: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const options = [
    {
      label: "Developer",
      body: "Memory for your product's agents.",
      href: `${appUrl}/login?mode=register&next=${encodeURIComponent("/developer")}`,
    },
    {
      label: "Personal",
      body: "Memory for your own coding agents.",
      href: `${appUrl}/login?mode=register`,
    },
  ];

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-[46px] items-center gap-2 rounded-[10px] bg-brand px-5 text-[15px] font-medium text-white transition hover:bg-brand-hover"
      >
        Get started
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-[calc(100%+8px)] z-20 w-[300px] overflow-hidden rounded-[12px] border border-border bg-white shadow-[0_16px_40px_-12px_rgba(0,0,0,0.18)]"
        >
          {options.map((o) => (
            <a
              key={o.label}
              role="menuitem"
              href={o.href}
              className="block border-b border-border-subtle px-4 py-3.5 transition last:border-b-0 hover:bg-surface"
            >
              <span className="block text-[15px] font-medium text-ink">{o.label}</span>
              <span className="mt-0.5 block text-[13.5px] text-dim">{o.body}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
