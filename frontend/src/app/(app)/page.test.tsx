import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";

vi.mock("@/lib/api", () => ({
  API_BASE: "",
  githubOwner: () => "",
  listPublicPages: vi.fn(async () => [
    {
      slug: "my-page-abc123",
      title: "My page",
      content_type: "markdown",
      view_count: 3,
      created_at: "2026-01-01T00:00:00Z",
    },
  ]),
}));

vi.mock("@/components/skill/ForkSkillCardButton", () => ({
  default: () => null,
}));

describe("HomePage community page cards", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({ skills: [] }) })),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  // Community pages render inside the app at /pages/[slug], like skills do at
  // /skills/[slug] — the card must stay on the app origin and in the same tab.
  it("links community pages to the in-app viewer route", async () => {
    render(<HomePage />);
    const card = await screen.findByRole("link", { name: /my page/i });
    expect(card.getAttribute("href")).toBe("/pages/my-page-abc123");
    expect(card.getAttribute("target")).toBeNull();
  });
});
