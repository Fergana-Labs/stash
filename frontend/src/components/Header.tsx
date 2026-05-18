"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { User } from "../lib/types";
import { useEscapeKey } from "../hooks/useEscapeKey";

interface HeaderProps {
  user: User | null;
  onLogout?: () => void;
}

export default function Header({ user, onLogout }: HeaderProps) {
  return (
    <header className="bg-surface border-b border-border">
      <div className="px-4 py-2 flex items-center justify-end gap-4">
        {user ? (
          <HeaderUserMenu user={user} onLogout={onLogout} />
        ) : (
          <Link
            href="/login"
            className="text-sm bg-brand hover:bg-brand-hover text-foreground px-3 py-1.5 rounded"
          >
            Register / Login
          </Link>
        )}
      </div>
    </header>
  );
}

function HeaderUserMenu({ user, onLogout }: { user: User; onLogout?: () => void }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const label = user.display_name || user.name;
  const initial = (label || "?")[0].toUpperCase();

  useEscapeKey(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;

    function onDown(event: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={label}
        className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-[var(--color-brand-700)] hover:ring-2 hover:ring-[var(--color-brand-200)]"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1.5 w-44 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted">
            Signed in as <span className="text-foreground">{label}</span>
          </div>
          <Link
            href="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="block px-3 py-1.5 text-foreground hover:bg-raised"
          >
            Account settings
          </Link>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onLogout?.();
            }}
            className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
