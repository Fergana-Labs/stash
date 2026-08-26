"use client";

import { ReactNode, useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import DeveloperShell from "@/components/developer/DeveloperShell";
import { useScope } from "@/lib/scope-store";
import { useWorkspace } from "@/lib/workspace-store";
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
const EXPLORER_SECTIONS: ExplorerSection[] = ["files", "sessions", "skills", "agents", "tools", "computer"];

// Experiment (2026-08-10): only the VFS keeps the tree sidebar. Sessions,
// Skills, Tools, and Agents render full-width — the explorers were a second
// nav axis over the same content as the rail, and the two looked independent.
// Agents brings its own ChatGPT-style chat list; the VM (browser) keeps its
// panel because that content lives nowhere else.
const PANELLED_SECTIONS: ExplorerSection[] = ["files", "computer"];

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
 *  the wiki, Settings, published skill pages, …). Most sections
 *  render the tab workbench; `/sessions` keeps its full management page
 *  beside the Sessions explorer. */
function sectionForPath(pathname: string): ExplorerSection | null {
  if (pathname === "/files" || /^\/(p|f|folders|tables)\//.test(pathname)) return "files";
  if (pathname === "/sessions" || pathname.startsWith("/sessions/")) return "sessions";
  if (pathname === "/skills" || pathname.startsWith("/skills/folder")) return "skills";
  if (pathname === "/agents") return "agents";
  if (pathname === "/tools" || pathname.startsWith("/integrations")) return "tools";
  return null;
}

/** Routes whose page.tsx is a management page rendered beside the explorer.
 *  Everything else in a section shows the tab workbench — so a new management
 *  route MUST be added here or its page component never renders at all. */
export function rendersRouteContent(
  pathname: string,
  selectedSection: string | null,
  workspaceParam: string | null,
): boolean {
  if (selectedSection) return false;
  // The Files home is the bird's-eye view of the whole stash; opening any
  // item navigates to its own route, which returns to the workbench.
  if (pathname === "/files") return true;
  if (pathname === "/sessions") return workspaceParam !== "1";
  // The Skills home is the launcher — pick a skill, run it. Only the bare
  // path: /skills/folder/<id> is a skill you opened, which belongs in a tab.
  if (pathname === "/skills") return true;
  // The MCP-server registry is a management page like /sessions.
  if (pathname === "/tools") return true;
  // /agents is the ChatGPT-style chat page — its own sidebar, no workbench.
  return pathname === "/agents";
}


/**
 * The app shell — icon rail + top bar + main area. Each primary rail section
 * (Files/Sessions/Skills/Agents/Tools) shows its own explorer panel. The Files
 * section drives the tab workbench; other sections render their route content
 * beside the explorer. Secondary routes (Index/Settings) render full.
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
  const scope = useScope();
  const routeSection = sectionForPath(pathname);
  const requestedSection = searchParams.get("section");
  const selectedSection = EXPLORER_SECTIONS.find((s) => s === requestedSection) ?? null;
  const section = selectedSection ?? routeSection;
  const renderRouteContent = rendersRouteContent(
    pathname,
    selectedSection,
    searchParams.get("workspace"),
  );
  // Remember where the user is inside the VFS, so the rail's VFS button can
  // bring them back instead of restarting at the bare lens.
  const setLastVfsUrl = useWorkspace((s) => s.setLastVfsUrl);
  useEffect(() => {
    if (section !== "files") return;
    const query = searchParams.toString();
    setLastVfsUrl(query ? `${pathname}?${query}` : pathname);
  }, [section, pathname, searchParams, setLastVfsUrl]);

  // /files IS a file tree — showing the explorer's tree beside it would be
  // the same thing twice. An explicit ?section= still summons the panel.
  const isFilesHome = pathname === "/files" && !selectedSection;
  const showExplorer = section !== null && PANELLED_SECTIONS.includes(section) && !isFilesHome;

  // A Developer Console context gets its own chrome — the infra-dashboard
  // shell, not the consumer app's rail and workbench.
  if (scope?.view === "developer") {
    return (
      <>
        <DeveloperShell user={user} onLogout={onLogout}>
          {children}
        </DeveloperShell>
        <Toaster />
      </>
    );
  }

  return (
    // Chrome surface — the content panel floats on top of it.
    <div className="flex h-screen flex-col overflow-hidden bg-sidebar">
      <Persistence />
      <Topbar />
      <div className="flex min-h-0 flex-1">
        <Rail user={user} onLogout={onLogout} />
        <div className="min-w-0 flex-1 pb-0">
          {section && !isFilesHome ? (
            <div className="flex h-full">
              {showExplorer && <ExplorerPanel section={section} />}
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
