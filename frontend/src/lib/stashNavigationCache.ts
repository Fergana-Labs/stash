import {
  getFolderContents,
  getStashSidebar,
  listMyWorkspaces,
  type FolderContents,
  type StashSidebar,
} from "./api";
import type { Workspace } from "./types";

interface CachedWorkspaces {
  userId: string;
  all: Workspace[];
  mine: Workspace[];
  shared: Workspace[];
}

let workspaceCache: CachedWorkspaces | null = null;
let workspacePromise: Promise<CachedWorkspaces> | null = null;
const sidebarCache: Record<string, StashSidebar> = {};
const sidebarPromises: Partial<Record<string, Promise<StashSidebar>>> = {};
const folderContentsCache: Record<string, FolderContents> = {};
const folderContentsPromises: Partial<Record<string, Promise<FolderContents>>> = {};

export function readCachedWorkspaces(userId: string | undefined): CachedWorkspaces | null {
  if (!userId || workspaceCache?.userId !== userId) return null;
  return workspaceCache;
}

export async function getCachedWorkspaces(userId: string): Promise<CachedWorkspaces> {
  const cached = readCachedWorkspaces(userId);
  if (cached) return cached;
  if (workspacePromise) return workspacePromise;

  workspacePromise = listMyWorkspaces()
    .then((result) => {
      const all = result.workspaces ?? [];
      workspaceCache = {
        userId,
        all,
        mine: all.filter((workspace) => workspace.creator_id === userId),
        shared: all.filter((workspace) => workspace.creator_id !== userId),
      };
      return workspaceCache;
    })
    .finally(() => {
      workspacePromise = null;
    });

  return workspacePromise;
}

export function readCachedSidebars(): Record<string, StashSidebar> {
  return { ...sidebarCache };
}

export function readCachedStashSidebar(stashId: string): StashSidebar | null {
  return sidebarCache[stashId] ?? null;
}

export async function getCachedStashSidebar(stashId: string): Promise<StashSidebar> {
  const cached = readCachedStashSidebar(stashId);
  if (cached) return cached;
  const pending = sidebarPromises[stashId];
  if (pending) return pending;

  const promise = getStashSidebar(stashId)
    .then((sidebar) => {
      sidebarCache[stashId] = sidebar;
      return sidebar;
    })
    .finally(() => {
      delete sidebarPromises[stashId];
    });
  sidebarPromises[stashId] = promise;

  return promise;
}

export function readCachedFolderContents(folderId: string): FolderContents | null {
  return folderContentsCache[folderId] ?? null;
}

export async function getCachedFolderContents(
  stashId: string,
  folderId: string
): Promise<FolderContents> {
  const cached = readCachedFolderContents(folderId);
  if (cached) return cached;
  const pending = folderContentsPromises[folderId];
  if (pending) return pending;

  const promise = getFolderContents(stashId, folderId)
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

export function resetStashNavigationCache() {
  workspaceCache = null;
  workspacePromise = null;
  for (const key of Object.keys(sidebarCache)) delete sidebarCache[key];
  for (const key of Object.keys(sidebarPromises)) delete sidebarPromises[key];
  for (const key of Object.keys(folderContentsCache)) delete folderContentsCache[key];
  for (const key of Object.keys(folderContentsPromises)) delete folderContentsPromises[key];
}
