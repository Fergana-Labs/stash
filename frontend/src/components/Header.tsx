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
  const label = user.display_name;
  const accountLabel = user.email ?? user.name;
  const usernameLabel = `@${user.name}`;
  const initial = label[0].toUpperCase();

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
        title={accountLabel}
        className="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-full bg-brand-100 text-[11px] font-semibold text-[var(--color-brand-700)] hover:ring-2 hover:ring-[var(--color-brand-200)]"
      >
        {initial}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1.5 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg"
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            <div>
              Signed in as <span className="break-all text-foreground">{accountLabel}</span>
            </div>
            <div className="mt-0.5">
              Username <span className="break-all text-foreground">{usernameLabel}</span>
            </div>
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
            className="block w-full cursor-pointer px-3 py-1.5 text-left text-foreground hover:bg-raised"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
