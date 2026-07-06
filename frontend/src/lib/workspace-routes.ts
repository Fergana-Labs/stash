import type { TabKind, WorkbenchTab } from "@/lib/workspace-store";

/** Canonical permanent URL for a tab — the same route that deep-links/sharing use. */
export function urlForTab(tab: Pick<WorkbenchTab, "kind" | "refId">): string {
  switch (tab.kind) {
    case "page":
      return `/p/${tab.refId}`;
    case "file":
      return `/f/${tab.refId}`;
    case "table":
      return `/tables/${tab.refId}`;
    case "session":
      return `/sessions/${tab.refId}`;
    case "sessions-home":
      return "/sessions?workspace=1";
    case "skill":
      return `/skills/folder/${tab.refId}`;
    case "folder":
      return `/folders/${tab.refId}`;
    case "agent":
      return `/agents`;
    case "tool":
      return `/tools`;
    case "machine-file":
      // Machine files have no permanent route — they live on the box.
      return `/agents`;
    case "terminal":
      return `/agents`;
    case "agent-config":
      return `/agents`;
  }
}

/** Parse a content-detail pathname into the tab it represents (or null). Drives
 *  deep-link → tab: a shared /p, /f, /sessions/:id, or /skills/:slug opens its
 *  tab in the workbench. */
export function tabFromPath(pathname: string): { kind: TabKind; refId: string } | null {
  const page = pathname.match(/^\/p\/([^/?#]+)/);
  if (page) return { kind: "page", refId: decodeURIComponent(page[1]) };
  const file = pathname.match(/^\/f\/([^/?#]+)/);
  if (file) return { kind: "file", refId: decodeURIComponent(file[1]) };
  const table = pathname.match(/^\/tables\/([^/?#]+)/);
  if (table) return { kind: "table", refId: decodeURIComponent(table[1]) };
  const session = pathname.match(/^\/sessions\/([^/?#]+)/);
  if (session) return { kind: "session", refId: decodeURIComponent(session[1]) };
  const skillFolder = pathname.match(/^\/skills\/folder\/([^/?#]+)/);
  if (skillFolder) return { kind: "skill", refId: decodeURIComponent(skillFolder[1]) };
  const folder = pathname.match(/^\/folders\/([^/?#]+)/);
  if (folder) return { kind: "folder", refId: decodeURIComponent(folder[1]) };
  return null;
}
