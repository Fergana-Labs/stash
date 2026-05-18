import { describe, expect, it } from "vitest";
import { stashSlugFromInput } from "./stashLinks";

describe("stashSlugFromInput", () => {
  it("extracts a Stash slug from a full URL", () => {
    expect(stashSlugFromInput("https://joinstash.ai/stashes/partner-plan?x=1")).toBe(
      "partner-plan"
    );
  });

  it("extracts a Stash slug from a relative URL", () => {
    expect(stashSlugFromInput("/stashes/private-brief#top")).toBe("private-brief");
  });

  it("accepts a pasted slug", () => {
    expect(stashSlugFromInput("partner-plan")).toBe("partner-plan");
  });

  it("rejects unrelated URLs", () => {
    expect(stashSlugFromInput("https://joinstash.ai/workspaces/ws-1")).toBe("");
  });
});
