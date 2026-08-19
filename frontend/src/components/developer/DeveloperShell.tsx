"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Building2,
  KeyRound,
  LayoutDashboard,
  MessagesSquare,
  FolderTree,
} from "lucide-react";

import ScopeSwitcher from "@/components/workspace/scope-switcher";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: typeof BookOpen;
  match: (p: string) => boolean;
};

const PLATFORM: NavItem[] = [
  { href: "/developer", label: "Overview", icon: LayoutDashboard, match: (p) => p === "/developer" },
  { href: "/developer/orgs", label: "Orgs", icon: Building2, match: (p) => p.startsWith("/developer/orgs") },
  { href: "/developer/wiki", label: "Shared Wiki", icon: BookOpen, match: (p) => p.startsWith("/developer/wiki") || p.startsWith("/folders/") || p.startsWith("/p/") },
];

const DATA: NavItem[] = [
  { href: "/sessions", label: "Sessions", icon: MessagesSquare, match: (p) => p.startsWith("/sessions") },
  { href: "/files", label: "Files", icon: FolderTree, match: (p) => p === "/files" || p.startsWith("/f/") },
];

const DEVELOPER: NavItem[] = [
  { href: "/developer/keys", label: "API Keys", icon: KeyRound, match: (p) => p.startsWith("/developer/keys") },
];

function NavGroup({ label, items, pathname }: { label: string; items: NavItem[]; pathname: string }) {
  return (
    <div className="mb-5">
      <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-400">
        {label}
      </div>
      {items.map((item) => {
        const Icon = item.icon;
        const active = item.match(pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors",
              active
                ? "bg-zinc-100 font-medium text-zinc-900"
                : "text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900",
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}

/**
 * The Developer Console's own chrome — deliberately not the consumer app's.
 * White, dense, monochrome: a text sidebar with grouped sections and a thin
 * top bar, the visual language of an infra dashboard rather than a personal
 * knowledge tool. Swapped in by WorkspaceShell whenever Scope.view is
 * "developer"; the ScopeSwitcher in the top bar is the way back out.
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
    <div className="flex h-screen flex-col overflow-hidden bg-white text-zinc-900">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-zinc-200 px-4">
        <Link href="/developer" className="flex items-center gap-2">
          <span className="font-mono text-[13px] font-semibold tracking-tight">
            stash<span className="text-zinc-400">/dev</span>
          </span>
        </Link>
        <div className="h-4 w-px bg-zinc-200" />
        <ScopeSwitcher />
        <div className="ml-auto flex items-center gap-4">
          <a
            href="https://joinstash.ai/docs"
            target="_blank"
            rel="noreferrer"
            className="text-[12px] font-medium text-zinc-500 hover:text-zinc-900"
          >
            Docs ↗
          </a>
          <button
            onClick={onLogout}
            className="text-[12px] font-medium text-zinc-500 hover:text-zinc-900"
          >
            Sign out
          </button>
          <div
            title={user.email ?? user.name}
            className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-900 text-[11px] font-semibold text-white"
          >
            {user.display_name[0].toUpperCase()}
          </div>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav className="w-[210px] shrink-0 overflow-y-auto border-r border-zinc-200 px-2 py-4">
          <NavGroup label="Platform" items={PLATFORM} pathname={pathname} />
          <NavGroup label="Data" items={DATA} pathname={pathname} />
          <NavGroup label="Developer" items={DEVELOPER} pathname={pathname} />
        </nav>
        <main className="min-w-0 flex-1 overflow-y-auto bg-white">{children}</main>
      </div>
    </div>
  );
}
