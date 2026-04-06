"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const SEARCH: NavItem = { href: "/search", label: "Search", icon: "S" };

const ARTIFACTS: NavItem[] = [
  { href: "/notebooks", label: "Notebooks", icon: "N" },
  { href: "/documents", label: "Files", icon: "F" },
  { href: "/decks", label: "Pages", icon: "D" },
  { href: "/tables", label: "Tables", icon: "T" },
];

const AGENTS: NavItem[] = [
  { href: "/personas", label: "Personas", icon: "P" },
  { href: "/chats", label: "Chats", icon: "C" },
  { href: "/memory", label: "History", icon: "H" },
];

function NavLink({ item, isActive }: { item: NavItem; isActive: boolean }) {
  return (
    <Link
      href={item.href}
      className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
        isActive
          ? "bg-brand/10 text-brand font-medium"
          : "text-dim hover:text-foreground hover:bg-raised"
      }`}
    >
      <span
        className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
          isActive
            ? "bg-brand text-white"
            : "bg-raised text-muted"
        }`}
      >
        {item.icon}
      </span>
      {item.label}
    </Link>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] font-medium text-muted uppercase tracking-wider px-3 pt-4 pb-1">
      {children}
    </div>
  );
}

export default function AppSidebar() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  return (
    <aside className="w-[220px] flex-shrink-0 bg-surface border-r border-border flex flex-col">
      <div className="px-4 py-4">
        <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">
          boozle
        </Link>
      </div>

      <nav className="flex-1 px-2">
        <NavLink item={SEARCH} isActive={isActive(SEARCH.href)} />

        <SectionLabel>Artifacts</SectionLabel>
        <div className="space-y-0.5">
          {ARTIFACTS.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>

        <SectionLabel>Agents</SectionLabel>
        <div className="space-y-0.5">
          {AGENTS.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>
      </nav>

      {/* Workspace switcher at bottom */}
      <div className="px-2 pb-3">
        <Link
          href="/rooms"
          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
            isActive("/rooms")
              ? "bg-brand/10 text-brand font-medium"
              : "text-dim hover:text-foreground hover:bg-raised"
          }`}
        >
          <span
            className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
              isActive("/rooms")
                ? "bg-brand text-white"
                : "bg-raised text-muted"
            }`}
          >
            W
          </span>
          Workspaces
        </Link>
      </div>
    </aside>
  );
}
