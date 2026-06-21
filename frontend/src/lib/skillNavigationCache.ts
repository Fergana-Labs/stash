import {
  getFolderContents,
  getSidebar,
  type FolderContents,
  type Sidebar,
} from "./api";

let sidebarCache: Sidebar | null = null;
let sidebarPromise: Promise<Sidebar> | null = null;
const folderContentsCache: Record<string, FolderContents> = {};
const folderContentsPromises: Partial<Record<string, Promise<FolderContents>>> = {};

export function readCachedSidebar(): Sidebar | null {
  return sidebarCache;
}

export async function getCachedSidebar(): Promise<Sidebar> {
  if (sidebarCache) return sidebarCache;
  if (sidebarPromise) return sidebarPromise;

  sidebarPromise = getSidebar()
    .then((sidebar) => {
      sidebarCache = sidebar;
      return sidebar;
    })
    .finally(() => {
      sidebarPromise = null;
    });

  return sidebarPromise;
}

type SidebarSubscriber = (sidebar: Sidebar) => void;
const sidebarSubscribers = new Set<SidebarSubscriber>();

export function subscribeToSidebarRefresh(cb: SidebarSubscriber): () => void {
  sidebarSubscribers.add(cb);
  return () => {
    sidebarSubscribers.delete(cb);
  };
}

export async function refreshSidebar(): Promise<Sidebar> {
  const sidebar = await getSidebar();
  sidebarCache = sidebar;
  // Notify anyone listening (e.g. AppSidebar) so they can re-render.
  for (const cb of sidebarSubscribers) cb(sidebar);
  return sidebar;
}

export function readCachedFolderContents(folderId: string): FolderContents | null {
  return folderContentsCache[folderId] ?? null;
}

export async function getCachedFolderContents(folderId: string): Promise<FolderContents> {
  const cached = readCachedFolderContents(folderId);
  if (cached) return cached;
  const pending = folderContentsPromises[folderId];
  if (pending) return pending;

  const promise = getFolderContents(folderId)
    .then((contents) => {
      folderContentsCache[folderId] = contents;
      return contents;
    })
    .finally(() => {
      delete folderContentsPromises[folderId];
    });
  folderContentsPromises[folderId] = promise;

  return promise;
}

export function resetSkillNavigationCache() {
  sidebarCache = null;
  sidebarPromise = null;
  for (const key of Object.keys(folderContentsCache)) delete folderContentsCache[key];
  for (const key of Object.keys(folderContentsPromises)) delete folderContentsPromises[key];
}
