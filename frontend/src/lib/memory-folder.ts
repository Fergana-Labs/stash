import type { FolderBreadcrumb } from "@/lib/api";

export interface SectionCrumb {
  label: string;
  href: string;
  area?: "memory" | "files";
}

export function sectionCrumbs(chain: FolderBreadcrumb[]): SectionCrumb[] {
  if (chain[0]?.is_memory) {
    return chain.map((breadcrumb, index) => ({
      label: breadcrumb.name,
      href: index === 0 ? "/" : `/folders/${breadcrumb.id}`,
      area: index === 0 ? "memory" : undefined,
    }));
  }

  return [
    { label: "Files", href: "/files", area: "files" },
    ...chain.map((b) => ({ label: b.name, href: `/folders/${b.id}` })),
  ];
}
