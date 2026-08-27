import type { FolderBreadcrumb } from "@/lib/api";

export interface SectionCrumb {
  label: string;
  href: string;
  area?: "memory" | "files" | "skills";
}

export function sectionCrumbs(chain: FolderBreadcrumb[]): SectionCrumb[] {
  if (chain[0]?.is_memory) {
    return chain.map((breadcrumb, index) => ({
      label: breadcrumb.name,
      href: index === 0 ? "/" : `/folders/${breadcrumb.id}`,
      area: index === 0 ? "memory" : undefined,
    }));
  }

  const skillIndex = chain.findIndex((breadcrumb) => breadcrumb.is_skill);
  if (skillIndex !== -1) {
    return [
      { label: "Skills", href: "/skills", area: "skills" },
      ...chain.slice(skillIndex).map((breadcrumb) => ({
        label: breadcrumb.name,
        href: `/skills/folder/${breadcrumb.id}`,
      })),
    ];
  }

  return [
    { label: "Files", href: "/files", area: "files" },
    ...chain.map((b) => ({ label: b.name, href: `/files?folder=${b.id}` })),
  ];
}
