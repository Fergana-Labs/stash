import { describe, expect, it } from "vitest";
import { generateWelcomeHtml } from "./welcomeContent";

describe("generateWelcomeHtml", () => {
  it("omits the explanatory About-page copy from new workspaces", () => {
    const html = generateWelcomeHtml({
      displayName: "Ada",
      inviteLink: null,
      counts: {
        pages: 0,
        files: 0,
        sessions: 0,
      },
    });

    expect(html).toContain("<h1>Welcome to Stash, Ada</h1>");
    expect(html).toContain("<h2>What to try next</h2>");
    expect(html).not.toContain("This is your About page");
  });
});
