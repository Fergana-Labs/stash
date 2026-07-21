import type { TabKind, WorkbenchTab } from "@/lib/workspace-store";

// Single source of truth for app-internal route paths. Every deep link,
// share URL, and router.push in the frontend goes through these.
export const routes = {
  page: (id: string) => `/page/${id}`,
  file: (id: string) => `/file/${id}`,
  table: (id: string) => `/tables/${id}`,
  session: (id: string) => `/sessions/${encodeURIComponent(id)}`,
  folder: (id: string) => `/folders/${id}`,
  skill: (slug: string) => `/skills/${slug}`,
  skillFolder: (id: string) => `/skills/folder/${id}`,
  extension: "/extension",
};

/** Canonical permanent URL for a tab — the same route that deep-links/sharing use. */
export function urlForTab(tab: Pick<WorkbenchTab, "kind" | "refId">): string {
  switch (tab.kind) {
    case "page":
      return routes.page(tab.refId);
    case "file":
      return routes.file(tab.refId);
    case "table":
      return routes.table(tab.refId);
    case "session":
      return routes.session(tab.refId);
    case "sessions-home":
      return "/sessions?workspace=1";
    case "skill":
      return routes.skillFolder(tab.refId);
    case "folder":
      return routes.folder(tab.refId);
    case "agent": {
      const m = tab.refId.match(/^(?:agent-|new:)([a-zA-Z0-9_-]+)/);
      const id = m?.[1];
      if (id && !/^[0-9a-f]{32}$/i.test(id) && !id.startsWith("curate-") && !id.startsWith("sched-")) {
        return `/agents?agent=${id}`;
      }
      return `/agents?session=${tab.refId}`;
    }
    case "tool":
      // A provider slug deep-links to its manager; the legacy list stays /tools.
      return tab.refId === "integrations" ? `/tools` : `/integrations/${tab.refId}`;
    case "machine-file":
    case "terminal":
      return `/computer`;
    case "agent-config":
      return `/agents?config=${tab.refId}`;
  }
}

/** Parse a content-detail pathname into the tab it represents (or null). Drives
 *  deep-link → tab: a shared /p, /f, /sessions/:id, or /skills/:slug opens its
 *  tab in the workbench. */
export function tabFromPath(pathname: string): { kind: TabKind; refId: string } | null {
  const page = pathname.match(/^\/page\/([^/?#]+)/);
  if (page) return { kind: "page", refId: decodeURIComponent(page[1]) };
  const file = pathname.match(/^\/file\/([^/?#]+)/);
  if (file) return { kind: "file", refId: decodeURIComponent(file[1]) };
  const table = pathname.match(/^\/tables\/([^/?#]+)/);
  if (table) return { kind: "table", refId: decodeURIComponent(table[1]) };
  const session = pathname.match(/^\/sessions\/([^/?#]+)/);
  if (session) return { kind: "session", refId: decodeURIComponent(session[1]) };
  const skillFolder = pathname.match(/^\/skills\/folder\/([^/?#]+)/);
  if (skillFolder) return { kind: "skill", refId: decodeURIComponent(skillFolder[1]) };
  const folder = pathname.match(/^\/folders\/([^/?#]+)/);
  if (folder) return { kind: "folder", refId: decodeURIComponent(folder[1]) };
  const integration = pathname.match(/^\/integrations\/([^/?#]+)/);
  if (integration) return { kind: "tool", refId: decodeURIComponent(integration[1]) };
  return null;
}
