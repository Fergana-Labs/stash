"use client";

import Link from "next/link";
import { User } from "../lib/types";

interface HeaderProps {
  user: User | null;
  onLogout?: () => void;
}

export default function Header({ user, onLogout }: HeaderProps) {
  return (
    <header className="bg-surface border-b border-border">
      <div className="px-4 py-2 flex items-center justify-end gap-4">
        {user ? (
          <div className="flex items-center gap-3">
            <Link
              href="/settings"
              className="text-sm text-dim hover:text-foreground"
            >
              {user.display_name || user.name}
            </Link>
            <button
              onClick={onLogout}
              className="text-sm text-dim hover:text-foreground"
            >
              Logout
            </button>
          </div>
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
