import { describe, expect, it } from "vitest";
import { generateCollabIntroMarkdown } from "./collabIntro";

describe("generateCollabIntroMarkdown", () => {
  it("embeds the stored API key when self-hosted", () => {
    const md = generateCollabIntroMarkdown({
      displayName: "Ada",
      pageId: "page-1",
      apiKey: "self-hosted-key",
    });

    expect(md).toContain("Authenticate: export STASH_API_KEY=self-hosted-key");
    expect(md).toContain("stash files read-page page-1");
  });

  it("points managed Auth0 users at the CLI sign-in flow instead of a key", () => {
    const md = generateCollabIntroMarkdown({
      displayName: "Ada",
      pageId: "page-1",
      apiKey: null,
    });

    expect(md).toContain("Authenticate: stash login");
    expect(md).not.toContain("STASH_API_KEY");
    expect(md).toContain("stash files read-page page-1");
  });
});
