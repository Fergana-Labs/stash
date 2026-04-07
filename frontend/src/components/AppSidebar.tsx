"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { listMyWorkspaces } from "../lib/api";
import type { Workspace } from "../lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const SEARCH: NavItem = { href: "/search", label: "Search", icon: "S" };

const INGEST: NavItem[] = [
  { href: "/documents", label: "Files", icon: "F" },
  { href: "/memory", label: "History", icon: "H" },
  { href: "/tables", label: "Tables", icon: "T" },
];

const CURATE: NavItem[] = [
  { href: "/notebooks", label: "Notebooks", icon: "N" },
  { href: "/personas", label: "Personas", icon: "P" },
];

const SHARE: NavItem[] = [
  { href: "/chats", label: "Chats", icon: "C" },
  { href: "/decks", label: "Pages", icon: "D" },
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
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [showWsSwitcher, setShowWsSwitcher] = useState(false);

  useEffect(() => {
    listMyWorkspaces()
      .then((res) => setWorkspaces(res?.workspaces ?? []))
      .catch(() => {});
  }, []);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  // Detect current workspace from URL
  const wsMatch = pathname.match(/^\/workspaces\/([^/]+)/);
  const currentWsId = wsMatch?.[1];
  const currentWs = workspaces.find((w) => w.id === currentWsId);

  return (
    <aside className="w-[220px] flex-shrink-0 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-4 pt-4 pb-2">
        <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">
          boozle
        </Link>
      </div>

      {/* Workspace switcher */}
      <div className="px-2 pb-2 relative">
        <button
          onClick={() => setShowWsSwitcher(!showWsSwitcher)}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-dim hover:text-foreground hover:bg-raised transition-colors"
        >
          <span className="w-5 h-5 rounded bg-raised text-muted flex items-center justify-center text-[10px] font-bold flex-shrink-0">
            W
          </span>
          <span className="flex-1 text-left truncate">
            {currentWs?.name || "Workspaces"}
          </span>
          <span className="text-muted text-xs">{showWsSwitcher ? "▴" : "▾"}</span>
        </button>

        {showWsSwitcher && (
          <div className="absolute left-2 right-2 top-full z-50 bg-base border border-border rounded-lg shadow-lg py-1 mt-1">
            {workspaces.map((ws) => (
              <Link
                key={ws.id}
                href={`/workspaces/${ws.id}`}
                onClick={() => setShowWsSwitcher(false)}
                className={`block px-3 py-1.5 text-sm transition-colors ${
                  ws.id === currentWsId
                    ? "text-brand bg-brand/5"
                    : "text-foreground hover:bg-raised"
                }`}
              >
                {ws.name}
              </Link>
            ))}
            {workspaces.length === 0 && (
              <div className="px-3 py-1.5 text-xs text-muted">No workspaces yet</div>
            )}
            <div className="border-t border-border mt-1 pt-1">
              <Link
                href="/rooms"
                onClick={() => setShowWsSwitcher(false)}
                className="flex items-center gap-2 px-3 py-1.5 text-xs text-muted hover:text-foreground transition-colors"
              >
                Manage workspaces...
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 overflow-y-auto">
        <NavLink item={SEARCH} isActive={isActive(SEARCH.href)} />

        <SectionLabel>Ingest</SectionLabel>
        <div className="space-y-0.5">
          {INGEST.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>

        <SectionLabel>Curate</SectionLabel>
        <div className="space-y-0.5">
          {CURATE.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>

        <SectionLabel>Share</SectionLabel>
        <div className="space-y-0.5">
          {SHARE.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>
      </nav>

      {/* Docs + Settings */}
      <div className="px-2 pb-3 space-y-0.5">
        <Link
          href="/docs"
          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
            isActive("/docs")
              ? "bg-brand/10 text-brand font-medium"
              : "text-dim hover:text-foreground hover:bg-raised"
          }`}
        >
          <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold flex-shrink-0 ${
            isActive("/docs") ? "bg-brand text-white" : "bg-raised text-muted"
          }`}>?</span>
          Docs
        </Link>
      </div>
    </aside>
  );
}
