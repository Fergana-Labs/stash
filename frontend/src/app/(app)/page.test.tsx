import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";

// jsdom has no IntersectionObserver; the feed only uses it for infinite
// scroll, which these tests don't exercise.
vi.stubGlobal(
  "IntersectionObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

const getHomeFeed = vi.fn(async () => ({
  items: [
    {
      kind: "public_page",
      data: {
        slug: "my-page-abc123",
        title: "My page",
        content_type: "markdown",
        view_count: 3,
        created_at: "2026-01-01T00:00:00Z",
      },
    },
    {
      kind: "resurface",
      data: {
        source: "clip",
        title: "Why wikis compound",
        preview: "a saved article body",
        saved_at: "2026-01-01T00:00:00Z",
        app_url: "/p/11111111-1111-1111-1111-111111111111",
        external_url: null,
        image_url: null,
      },
    },
    {
      kind: "resurface",
      data: {
        source: "x",
        title: "@someone - 9001",
        preview: "an old banger",
        saved_at: "2026-01-01T00:00:00Z",
        app_url: null,
        external_url: "https://x.com/i/status/9001",
        image_url: null,
      },
    },
  ],
  next_cursor: null,
}));

vi.mock("@/lib/api", () => ({
  API_BASE: "",
  githubOwner: () => "",
  getHomeFeed: (...args: unknown[]) => getHomeFeed(...(args as [number])),
}));

vi.mock("@/components/skill/ForkSkillCardButton", () => ({
  default: () => null,
}));

describe("HomePage feed", () => {
  afterEach(() => {
    cleanup();
  });

  // Community pages render inside the app at /pages/[slug], like skills do at
  // /skills/[slug] — the card must stay on the app origin and in the same tab.
  it("links community pages to the in-app viewer route", async () => {
    render(<HomePage />);
    const card = await screen.findByRole("link", { name: /my page/i });
    expect(card.getAttribute("href")).toBe("/pages/my-page-abc123");
    expect(card.getAttribute("target")).toBeNull();
  });

  // A resurfaced clip is our own archived copy — it opens in-app; a
  // resurfaced X save has no in-app viewer, so it opens the original post
  // in a new tab.
  it("routes resurfaced items by their source", async () => {
    render(<HomePage />);
    const clip = await screen.findByRole("link", { name: /why wikis compound/i });
    expect(clip.getAttribute("href")).toBe("/p/11111111-1111-1111-1111-111111111111");
    const save = await screen.findByRole("link", { name: /9001/i });
    expect(save.getAttribute("href")).toBe("https://x.com/i/status/9001");
    expect(save.getAttribute("target")).toBe("_blank");
  });
});
