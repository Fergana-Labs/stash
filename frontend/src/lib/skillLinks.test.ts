import { describe, expect, it } from "vitest";
import { skillSlugFromInput } from "./skillLinks";

describe("skillSlugFromInput", () => {
  it("extracts a Skill slug from a full URL", () => {
    expect(skillSlugFromInput("https://joinstash.ai/skills/partner-plan?x=1")).toBe(
      "partner-plan"
    );
  });

  it("extracts a Skill slug from a relative URL", () => {
    expect(skillSlugFromInput("/skills/private-brief#top")).toBe("private-brief");
  });

  it("accepts a pasted slug", () => {
    expect(skillSlugFromInput("partner-plan")).toBe("partner-plan");
  });

  it("rejects unrelated URLs", () => {
    expect(skillSlugFromInput("https://joinstash.ai/files/file-1")).toBe("");
  });
});
