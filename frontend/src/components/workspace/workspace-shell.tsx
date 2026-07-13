"use client";

import { ReactNode, useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import type { User } from "@/lib/types";
import { Toaster } from "@/components/ui/sonner";
import Persistence from "./persistence";
import Rail from "./rail";
import Topbar from "./topbar";
import Explorer, { type ExplorerSection } from "./explorer";
import Workbench from "./workbench";

const WIDTH_KEY = "moltchat_explorer_width";
const MIN_W = 220;
const MAX_W = 600;
const EXPLORER_SECTIONS: ExplorerSection[] = ["files", "sessions", "skills", "agents", "memory", "tools", "computer"];

/** Resizable explorer panel — drag the right edge to set width (persisted). */
function ExplorerPanel({ section }: { section: ExplorerSection }) {
  const [width, setWidth] = useState(300);
  useEffect(() => {
    const saved = Number(localStorage.getItem(WIDTH_KEY));
    if (Number.isFinite(saved) && saved >= MIN_W && saved <= MAX_W) setWidth(saved);
  }, []);

  function startResize(e: React.PointerEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    const onMove = (ev: PointerEvent) => setWidth(Math.min(MAX_W, Math.max(MIN_W, Math.round(startW + ev.clientX - startX))));
    const stop = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
      setWidth((w) => { localStorage.setItem(WIDTH_KEY, String(w)); return w; });
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
  }

  return (
    <div className="relative shrink-0 border-r border-t border-sidebar-border" style={{ width }}>
      <Explorer section={section} />
      <div
        onPointerDown={startResize}
        className="group absolute inset-y-0 -right-1 z-20 w-2 cursor-col-resize touch-none"
        role="separator"
        aria-orientation="vertical"
      >
        <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-brand-300" />
      </div>
    </div>
  );
}

/** Which workspace section a path belongs to (null = full-page route: Home,
 *  Index, Discover, Settings, published skill pages, …). Most sections render
 *  the tab workbench; `/sessions` keeps its full management page beside the
 *  Sessions explorer. */
function sectionForPath(pathname: string): ExplorerSection | null {
  if (pathname === "/files" || /^\/(p|f|folders|tables)\//.test(pathname)) return "files";
  if (pathname === "/sessions" || pathname.startsWith("/sessions/") || pathname.startsWith("/session-folders")) return "sessions";
  if (pathname === "/skills" || pathname.startsWith("/skills/folder")) return "skills";
  if (pathname === "/agents") return "agents";
  if (pathname === "/memory" || pathname.startsWith("/memory/")) return "memory";
  if (pathname === "/tools") return "tools";
  return null;
}

/**
 * The app shell — icon rail + top bar + main area. Each primary rail section
 * (Files/Sessions/Skills/Agents/Tools) shows its own explorer panel. The Files
 * section drives the tab workbench; other sections render their route content
 * beside the explorer. Secondary routes (Index/Discover/Settings) render full.
 */
export default function WorkspaceShell({
  user,
  onLogout,
  children,
}: {
  user: User;
  onLogout: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const routeSection = sectionForPath(pathname);
  const requestedSection = searchParams.get("section");
  const selectedSection = EXPLORER_SECTIONS.find((s) => s === requestedSection) ?? null;
  const section = selectedSection ?? routeSection;
  const renderRouteContent =
    (pathname === "/sessions" && !selectedSection && searchParams.get("workspace") !== "1") ||
    // Memory routes (brain dashboard, wiki file system) render as pages
    // beside the explorer; opening an item switches to the workbench.
    (pathname.startsWith("/memory") && !selectedSection);

  return (
    // Chrome surface — the content panel floats on top of it.
    <div className="flex h-screen flex-col overflow-hidden bg-sidebar">
      <Persistence />
      <Topbar />
      <div className="flex min-h-0 flex-1">
        <Rail user={user} onLogout={onLogout} />
        <div className="min-w-0 flex-1 pb-0">
          {section ? (
            <div className="flex h-full">
              <ExplorerPanel section={section} />
              {/* Floating content panel: clean white paper, subtly elevated. */}
              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-tl-2xl border-l border-t border-border bg-base shadow-[-10px_-6px_28px_-16px_rgba(30,25,15,0.10)]">
                {renderRouteContent ? (
                  <main className="flex h-full min-h-0 flex-col overflow-hidden">{children}</main>
                ) : (
                  <Workbench />
                )}
              </div>
            </div>
          ) : (
            <main className="h-full overflow-y-auto rounded-tl-2xl border-l border-t border-border bg-base shadow-[-10px_-6px_28px_-16px_rgba(30,25,15,0.10)]">{children}</main>
          )}
        </div>
      </div>
      <Toaster />
    </div>
  );
}
