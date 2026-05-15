import {
  getFolderContents,
  getWorkspaceSidebar,
  listMyWorkspaces,
  type FolderContents,
  type WorkspaceSidebar,
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
const sidebarCache: Record<string, WorkspaceSidebar> = {};
const sidebarPromises: Partial<Record<string, Promise<WorkspaceSidebar>>> = {};
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

export function readCachedSidebars(): Record<string, WorkspaceSidebar> {
  return { ...sidebarCache };
}

export function readCachedWorkspaceSidebar(workspaceId: string): WorkspaceSidebar | null {
  return sidebarCache[workspaceId] ?? null;
}

export async function getCachedWorkspaceSidebar(workspaceId: string): Promise<WorkspaceSidebar> {
  const cached = readCachedWorkspaceSidebar(workspaceId);
  if (cached) return cached;
  const pending = sidebarPromises[workspaceId];
  if (pending) return pending;

  const promise = getWorkspaceSidebar(workspaceId)
    .then((sidebar) => {
      sidebarCache[workspaceId] = sidebar;
      return sidebar;
    })
    .finally(() => {
      delete sidebarPromises[workspaceId];
    });
  sidebarPromises[workspaceId] = promise;

  return promise;
}

export async function refreshWorkspaceSidebar(workspaceId: string): Promise<WorkspaceSidebar> {
  const sidebar = await getWorkspaceSidebar(workspaceId);
  sidebarCache[workspaceId] = sidebar;
  return sidebar;
}

export function readCachedFolderContents(folderId: string): FolderContents | null {
  return folderContentsCache[folderId] ?? null;
}

export async function getCachedFolderContents(
  workspaceId: string,
  folderId: string
): Promise<FolderContents> {
  const cached = readCachedFolderContents(folderId);
  if (cached) return cached;
  const pending = folderContentsPromises[folderId];
  if (pending) return pending;

  const promise = getFolderContents(workspaceId, folderId)
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
