"use client";

import { useEffect, useState } from "react";

import { getMemoryFolder, type FolderBreadcrumb } from "@/lib/api";

/** Memory is its own space — a reserved system folder (backend-enforced: one
 *  per user, hidden from Files, can't be renamed/moved/deleted). */
export function useMemoryFolderId(): string | null {
  const [id, setId] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    getMemoryFolder().then((f) => { if (!cancelled) setId(f.id); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);
  return id;
}

export interface SectionCrumb {
  label: string;
  href: string;
}

/** Ancestor crumbs for a folder chain, rooted at the section the chain lives
 *  in. Files and Memory are MECE sections over one folder tree, so a chain
 *  containing the memory folder roots at Memory (and its links carry
 *  ?section=memory so the shell keeps the Memory panel open) — everything
 *  else roots at Files. */
export function sectionCrumbs(
  chain: FolderBreadcrumb[],
  memoryFolderId: string | null,
): SectionCrumb[] {
  const inMemory = !!memoryFolderId && chain.some((b) => b.id === memoryFolderId);
  const suffix = inMemory ? "?section=memory" : "";
  const root = inMemory
    ? { label: "Memory", href: "/memory" }
    : { label: "Files", href: "/files" };
  return [
    root,
    ...chain
      .filter((b) => b.id !== memoryFolderId)
      .map((b) => ({ label: b.name, href: `/folders/${b.id}${suffix}` })),
  ];
}
