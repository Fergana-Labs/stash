import { describe, expect, it } from "vitest";
import { sectionCrumbs } from "./skill-breadcrumbs";

describe("sectionCrumbs", () => {
  it("walks plain uploaded folders without a section root", () => {
    expect(sectionCrumbs([])).toEqual([]);
    expect(
      sectionCrumbs([
        { id: "imports", name: "Imports", is_skill: false, is_curated_skill: false },
      ]),
    ).toEqual([{ label: "Imports", href: "/folders/imports" }]);
  });

  it("roots curated knowledge at Skills", () => {
    expect(
      sectionCrumbs([
        { id: "curated", name: "Learned knowledge", is_skill: true, is_curated_skill: true },
        {
          id: "platform",
          name: "Platform & Data",
          is_skill: false,
          is_curated_skill: false,
        },
      ]),
    ).toEqual([
      { label: "Skills", href: "/skills", area: "skills" },
      { label: "Learned knowledge", href: "/skills/folder/curated" },
      { label: "Platform & Data", href: "/skills/folder/platform" },
    ]);
  });

  it("keeps supporting content inside its Skill", () => {
    expect(
      sectionCrumbs([
        {
          id: "ordinary-parent",
          name: "Imports",
          is_skill: false,
          is_curated_skill: false,
        },
        {
          id: "skill-root",
          name: "Partner Briefs",
          is_skill: true,
          is_curated_skill: false,
        },
        { id: "research", name: "Research", is_skill: false, is_curated_skill: false },
      ]),
    ).toEqual([
      { label: "Skills", href: "/skills", area: "skills" },
      { label: "Partner Briefs", href: "/skills/folder/skill-root" },
      { label: "Research", href: "/skills/folder/research" },
    ]);
  });
});
