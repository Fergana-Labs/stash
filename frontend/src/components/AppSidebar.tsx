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

const CONSUME: NavItem[] = [
  { href: "/documents", label: "Files", icon: "F" },
  { href: "/memory", label: "History", icon: "H" },
  { href: "/tables", label: "Tables", icon: "T" },
];

const CURATE: NavItem[] = [
  { href: "/notebooks", label: "Notebooks", icon: "N" },
  { href: "/personas", label: "Personas", icon: "P" },
];

const COLLABORATE: NavItem[] = [
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

const WS_STORAGE_KEY = "boozle_selected_workspace";

export default function AppSidebar() {
  const pathname = usePathname();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWsId, setSelectedWsId] = useState<string | null>(null);
  const [showWsSwitcher, setShowWsSwitcher] = useState(false);

  // Load workspaces + restore selection
  useEffect(() => {
    listMyWorkspaces()
      .then((res) => {
        const ws = res?.workspaces ?? [];
        setWorkspaces(ws);
        // Restore from localStorage, or select first
        const saved = typeof window !== "undefined" ? localStorage.getItem(WS_STORAGE_KEY) : null;
        if (saved && ws.some((w) => w.id === saved)) {
          setSelectedWsId(saved);
        } else if (ws.length > 0) {
          setSelectedWsId(ws[0].id);
        }
      })
      .catch(() => {});
  }, []);

  // Detect workspace from URL (overrides localStorage)
  useEffect(() => {
    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)/);
    if (wsMatch?.[1]) {
      setSelectedWsId(wsMatch[1]);
      localStorage.setItem(WS_STORAGE_KEY, wsMatch[1]);
    }
  }, [pathname]);

  const selectWorkspace = (wsId: string) => {
    setSelectedWsId(wsId);
    localStorage.setItem(WS_STORAGE_KEY, wsId);
    setShowWsSwitcher(false);
  };

  const selectedWs = workspaces.find((w) => w.id === selectedWsId);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

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
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
            selectedWs ? "text-foreground bg-raised" : "text-dim hover:text-foreground hover:bg-raised"
          }`}
        >
          <span className="w-5 h-5 rounded bg-brand/15 text-brand flex items-center justify-center text-[10px] font-bold flex-shrink-0">
            W
          </span>
          <span className="flex-1 text-left truncate font-medium">
            {selectedWs?.name || "Select workspace"}
          </span>
          <span className="text-muted text-xs">{showWsSwitcher ? "\u25B4" : "\u25BE"}</span>
        </button>

        {showWsSwitcher && (
          <>
            {/* Backdrop to close dropdown */}
            <div className="fixed inset-0 z-40" onClick={() => setShowWsSwitcher(false)} />
            <div className="absolute left-2 right-2 top-full z-50 bg-surface border border-border rounded-lg shadow-xl py-1 mt-1">
              {workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => selectWorkspace(ws.id)}
                  className={`block w-full text-left px-3 py-2 text-sm transition-colors ${
                    ws.id === selectedWsId
                      ? "text-brand bg-brand/5 font-medium"
                      : "text-foreground hover:bg-raised"
                  }`}
                >
                  <div className="truncate">{ws.name}</div>
                  {ws.description && (
                    <div className="text-[10px] text-muted truncate">{ws.description}</div>
                  )}
                </button>
              ))}
              {workspaces.length === 0 && (
                <div className="px-3 py-2 text-xs text-muted">No workspaces yet</div>
              )}
              <div className="border-t border-border mt-1 pt-1">
                <Link
                  href="/rooms"
                  onClick={() => setShowWsSwitcher(false)}
                  className="block px-3 py-1.5 text-xs text-muted hover:text-foreground transition-colors"
                >
                  Manage workspaces...
                </Link>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Navigation — scoped to selected workspace */}
      <nav className="flex-1 px-2 overflow-y-auto">
        <NavLink item={SEARCH} isActive={isActive(SEARCH.href)} />

        <SectionLabel>Consume</SectionLabel>
        <div className="space-y-0.5">
          {CONSUME.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>

        <SectionLabel>Curate</SectionLabel>
        <div className="space-y-0.5">
          {CURATE.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>

        <SectionLabel>Collaborate</SectionLabel>
        <div className="space-y-0.5">
          {COLLABORATE.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} />
          ))}
        </div>
      </nav>

      {/* Docs */}
      <div className="px-2 pb-3">
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
