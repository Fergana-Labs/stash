"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import ScopeSwitcher from "@/components/workspace/scope-switcher";
import { StashIcon } from "@/components/SkillIcons";
import { cn } from "@/lib/utils";
import type { User } from "@/lib/types";

type NavItem = { href: string; label: string; match: (p: string) => boolean };

const NAV: { title: string; items: NavItem[] }[] = [
  {
    title: "Platform",
    items: [
      { href: "/developer", label: "Overview", match: (p) => p === "/developer" },
      { href: "/developer/orgs", label: "Orgs", match: (p) => p.startsWith("/developer/orgs") },
      {
        href: "/developer/wiki",
        label: "Shared Wiki",
        match: (p) => p.startsWith("/developer/wiki"),
      },
    ],
  },
  {
    title: "Data",
    items: [
      { href: "/sessions", label: "Sessions", match: (p) => p.startsWith("/sessions") },
      { href: "/files", label: "Files", match: (p) => p === "/files" || p.startsWith("/f/") },
    ],
  },
  {
    title: "Developer",
    items: [
      { href: "/developer/keys", label: "API Keys", match: (p) => p.startsWith("/developer/keys") },
    ],
  },
];

/**
 * The Developer Platform's chrome, built to the landing site's docs layout
 * (`www/app/docs/layout.tsx`): warm paper page, a sticky hairline header, a
 * rounded sidebar card of text-only nav, and the content in a single rounded
 * panel. `data-surface="developer"` is what swaps the brand tokens underneath
 * it — see the block in globals.css.
 *
 * Swapped in by WorkspaceShell whenever Scope.view is "developer"; the
 * ScopeSwitcher in the header is the way back out.
 */
export default function DeveloperShell({
  user,
  onLogout,
  children,
}: {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div data-surface="developer" className="min-h-screen bg-base">
      <header className="sticky top-0 z-30 border-b border-border-subtle bg-base/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-6 md:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <Link
              href="/developer"
              aria-label="Stash Developer Platform"
              className="flex shrink-0 items-center gap-2 text-brand-500"
            >
              <StashIcon className="text-[24px]" />
              <span className="font-display text-[20px] font-semibold tracking-tight text-foreground">
                Stash
              </span>
            </Link>
            <span className="hidden font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground sm:block">
              Developer Platform
            </span>
            <ScopeSwitcher />
          </div>
          <nav className="flex items-center gap-6 text-[14px] text-dim">
            <a
              href="https://joinstash.ai/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden hover:text-foreground sm:block"
            >
              Docs
            </a>
            <button onClick={onLogout} className="hover:text-foreground">
              Sign out
            </button>
            <span
              title={user.email ?? user.name}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-500 font-mono text-[11px] font-medium text-white"
            >
              {user.display_name[0].toUpperCase()}
            </span>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-[1440px] px-6 py-8 md:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-[220px_minmax(0,1fr)] lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-10">
          <aside className="hidden md:block">
            <nav className="sticky top-24 rounded-2xl border border-border bg-surface p-4">
              {NAV.map((section) => (
                <div key={section.title} className="mb-5 last:mb-0">
                  <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                    {section.title}
                  </div>
                  <div className="space-y-1">
                    {section.items.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "block rounded-lg px-3 py-2 text-[13px] transition-colors",
                          item.match(pathname)
                            ? "bg-brand-500/10 font-medium text-brand-500"
                            : "text-dim hover:bg-raised hover:text-foreground",
                        )}
                      >
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </aside>

          <main className="min-w-0">
            <div className="rounded-[28px] border border-border bg-base px-6 py-8 sm:px-8 md:px-10">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
