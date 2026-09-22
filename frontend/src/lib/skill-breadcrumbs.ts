import type { FolderBreadcrumb } from "@/lib/api";

export interface SectionCrumb {
  label: string;
  href: string;
  area?: "skills";
}

export function sectionCrumbs(chain: FolderBreadcrumb[]): SectionCrumb[] {
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

  return chain.map((b) => ({ label: b.name, href: `/folders/${b.id}` }));
}
