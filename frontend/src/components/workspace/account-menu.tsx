"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useEscapeKey } from "@/hooks/useEscapeKey";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/types";

/** The account control — avatar opens a small menu (settings + sign out).
 *  The single home for account actions, shared by the workspace rail
 *  (bottom-left, menu opens up-right) and the developer console header
 *  (top-right, menu opens down-left). */
export default function AccountMenu({
  user,
  onLogout,
  placement = "rail",
}: {
  user: User;
  onLogout: () => void;
  placement?: "rail" | "header";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEscapeKey(open, () => setOpen(false));
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={user.email ?? user.name}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-500 text-[12px] font-semibold text-white hover:ring-2 hover:ring-brand-200"
      >
        {user.display_name[0].toUpperCase()}
      </button>
      {open && (
        <div
          role="menu"
          className={cn(
            "absolute z-40 w-56 overflow-hidden rounded-md border border-border bg-surface py-1 text-[13px] shadow-lg",
            placement === "rail" ? "bottom-0 left-full ml-2" : "top-full right-0 mt-2",
          )}
        >
          <div className="border-b border-border px-3 py-1.5 text-[11px] text-muted-foreground">
            Signed in as <span className="break-all text-foreground">{user.email ?? user.name}</span>
          </div>
          <Link href="/settings" onClick={() => setOpen(false)} className="block px-3 py-1.5 text-foreground hover:bg-raised">
            Account settings
          </Link>
          <button onClick={() => { setOpen(false); onLogout(); }} className="block w-full px-3 py-1.5 text-left text-foreground hover:bg-raised">
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
