import { describe, expect, it } from "vitest";
import { sectionCrumbs } from "./memory-folder";

describe("sectionCrumbs", () => {
  it("walks plain uploaded folders without a section root", () => {
    expect(sectionCrumbs([])).toEqual([]);
    expect(
      sectionCrumbs([
        { id: "imports", name: "Imports", is_skill: false, is_memory: false },
      ]),
    ).toEqual([{ label: "Imports", href: "/folders/imports" }]);
  });

  it("roots curator content at Memory", () => {
    expect(
      sectionCrumbs([
        { id: "memory", name: "Memory", is_skill: false, is_memory: true },
        {
          id: "platform",
          name: "Platform & Data",
          is_skill: false,
          is_memory: false,
        },
      ]),
    ).toEqual([
      { label: "Memory", href: "/", area: "memory" },
      { label: "Platform & Data", href: "/folders/platform" },
    ]);
  });

  it("keeps supporting content inside its Skill", () => {
    expect(
      sectionCrumbs([
        {
          id: "ordinary-parent",
          name: "Imports",
          is_skill: false,
          is_memory: false,
        },
        {
          id: "skill-root",
          name: "Partner Briefs",
          is_skill: true,
          is_memory: false,
        },
        { id: "research", name: "Research", is_skill: false, is_memory: false },
      ]),
    ).toEqual([
      { label: "Skills", href: "/skills", area: "skills" },
      { label: "Partner Briefs", href: "/skills/folder/skill-root" },
      { label: "Research", href: "/skills/folder/research" },
    ]);
  });
});
