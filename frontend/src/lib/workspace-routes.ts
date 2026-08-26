import type { TabKind, WorkbenchTab } from "@/lib/workspace-store";

// Single source of truth for app-internal route paths.
export const routes = {
  extension: "/extension",
};

/** Tab kinds whose permanent URL renders the workbench. The workbench pushes
 *  urlForTab on every focus, so a kind missing from this list is a tab you can
 *  open but never click back into — focusing it navigates the strip away.
 *  workspace-store migrates persisted tabs against this list. */
export const WORKBENCH_TAB_KINDS: TabKind[] = [
  "page",
  "file",
  "table",
  "session",
  "sessions-home",
  "skill",
  "folder",
  "tool",
];

/** Tabs that live only inside the workbench: the cloud box's terminal and its
 *  files exist on the box, not at an address. Opening or refocusing one must
 *  leave the URL alone — ask urlForTab for one and it throws, by design. */
const WORKBENCH_ONLY_KINDS: TabKind[] = ["machine-file", "terminal"];

export function hasPermanentUrl(kind: TabKind): boolean {
  return !WORKBENCH_ONLY_KINDS.includes(kind);
}

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
    case "tool":
      // A provider slug deep-links to its manager; the legacy list stays /tools.
      return tab.refId === "integrations" ? `/tools` : `/integrations/${tab.refId}`;
    case "machine-file":
    case "terminal":
      // These exist only inside the workbench — nothing routes to them, so
      // there is no honest URL to hand back.
      throw new Error(`${tab.kind} tabs have no permanent URL`);
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
  const integration = pathname.match(/^\/integrations\/([^/?#]+)/);
  if (integration) return { kind: "tool", refId: decodeURIComponent(integration[1]) };
  return null;
}
