import { describe, expect, it } from "vitest";
import { sectionCrumbs } from "./memory-folder";

describe("sectionCrumbs", () => {
  it("roots uploaded content at Files", () => {
    expect(sectionCrumbs([])).toEqual([{ label: "Files", href: "/files" }]);
  });

  it("roots curator content at Memory instead of Files", () => {
    expect(
      sectionCrumbs([
        { id: "memory", name: "Memory", is_skill: false, is_memory: true },
        { id: "platform", name: "Platform & Data", is_skill: false, is_memory: false },
      ]),
    ).toEqual([
      { label: "Memory", href: "/" },
      { label: "Platform & Data", href: "/folders/platform" },
    ]);
  });
});
