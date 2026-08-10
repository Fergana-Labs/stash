import type { FolderBreadcrumb } from "@/lib/api";

export interface SectionCrumb {
  label: string;
  href: string;
}

/** Ancestor crumbs for a folder chain, rooted at Files. The reserved Memory
 *  folder is an ordinary crumb in the chain — memory lives in the filesystem. */
export function sectionCrumbs(chain: FolderBreadcrumb[]): SectionCrumb[] {
  return [
    { label: "Files", href: "/files" },
    ...chain.map((b) => ({ label: b.name, href: `/folders/${b.id}` })),
  ];
}
