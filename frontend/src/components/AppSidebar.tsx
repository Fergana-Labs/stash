"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { listMyWorkspaces } from "../lib/api";
import type { Workspace } from "../lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/search", label: "Search", icon: "S" },
  { href: "/memory", label: "History", icon: "H" },
  { href: "/notebooks", label: "Wiki", icon: "W" },
];

function NavLink({ item, isActive, wsId }: { item: NavItem; isActive: boolean; wsId?: string | null }) {
  const href = wsId ? `${item.href}?ws=${wsId}` : item.href;
  return (
    <Link
      href={href}
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

const WS_STORAGE_KEY = "stash_selected_workspace";

export default function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWsId, setSelectedWsId] = useState<string | null>(null);
  const [showWsSwitcher, setShowWsSwitcher] = useState(false);

  // Load workspaces + restore selection
  useEffect(() => {
    listMyWorkspaces()
      .then((res) => {
        const ws = res?.workspaces ?? [];
        setWorkspaces(ws);
        const saved = typeof window !== "undefined" ? localStorage.getItem(WS_STORAGE_KEY) : null;
        if (saved && ws.some((w) => w.id === saved)) {
          setSelectedWsId(saved);
        } else if (ws.length > 0) {
          setSelectedWsId(ws[0].id);
        }
      })
      .catch(() => {});
  }, []);

  // Detect workspace from URL path or query param
  useEffect(() => {
    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)/);
    if (wsMatch?.[1]) {
      setSelectedWsId(wsMatch[1]);
      localStorage.setItem(WS_STORAGE_KEY, wsMatch[1]);
      return;
    }
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const wsParam = params.get("ws");
      if (wsParam) {
        setSelectedWsId(wsParam);
        localStorage.setItem(WS_STORAGE_KEY, wsParam);
      }
    }
  }, [pathname]);

  const selectWorkspace = (wsId: string) => {
    setSelectedWsId(wsId);
    localStorage.setItem(WS_STORAGE_KEY, wsId);
    setShowWsSwitcher(false);

    // If we're already inside a /workspaces/[id] route, swap the id. Otherwise
    // update the ?ws= query param on the current pathname so the page
    // re-fetches with the new workspace scope.
    const wsMatch = pathname.match(/^\/workspaces\/([^/]+)(.*)$/);
    if (wsMatch) {
      router.push(`/workspaces/${wsId}${wsMatch[2] ?? ""}`);
      return;
    }
    const params = new URLSearchParams(
      typeof window !== "undefined" ? window.location.search : ""
    );
    params.set("ws", wsId);
    router.push(`${pathname}?${params.toString()}`);
  };

  const selectedWs = workspaces.find((w) => w.id === selectedWsId);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  return (
    <aside className="w-[220px] flex-shrink-0 bg-surface border-r border-border flex flex-col">
      {/* Logo */}
      <div className="px-4 pt-4 pb-2">
        <Link href="/" className="text-lg font-bold font-display text-foreground tracking-tight">
          stash
        </Link>
      </div>

      {/* Workspace switcher */}
      <div className="px-2 pb-2 relative">
        <div className="w-full flex items-center gap-1 text-sm">
          <button
            onClick={() => selectedWsId && router.push(`/workspaces/${selectedWsId}`)}
            className={`flex-1 min-w-0 flex items-center gap-2 px-3 py-2 rounded-md transition-colors cursor-pointer hover:text-brand hover:bg-raised ${
              selectedWs ? "text-foreground bg-raised" : "text-dim"
            }`}
          >
            <span className="w-5 h-5 rounded bg-brand/15 text-brand flex items-center justify-center text-[10px] font-bold flex-shrink-0">
              W
            </span>
            <span className="flex-1 text-left truncate font-medium">
              {selectedWs?.name || "Select workspace"}
            </span>
          </button>
          <button
            onClick={() => setShowWsSwitcher(!showWsSwitcher)}
            className="flex-shrink-0 w-7 h-8 rounded-md text-muted text-xs hover:text-foreground hover:bg-raised cursor-pointer transition-colors flex items-center justify-center"
            aria-label="Switch workspace"
          >
            {showWsSwitcher ? "\u25B4" : "\u25BE"}
          </button>
        </div>

        {showWsSwitcher && (
          <>
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

      {/* Navigation */}
      <nav className="flex-1 px-2 overflow-y-auto">
        <div className="space-y-0.5">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} isActive={isActive(item.href)} wsId={selectedWsId} />
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
