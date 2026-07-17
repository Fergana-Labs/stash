import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// SSR_BACKEND_ORIGIN resolves from env at module load — set it before importing.
process.env.NEXT_PUBLIC_API_URL = "http://backend.test";
const { default: CommunityPage } = await import("./page");

function stubPaste(paste: object | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      paste ? { ok: true, json: async () => paste } : { ok: false },
    ),
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Home-screen community page cards link here — this route must exist in the
// app (they previously pointed at a route that only existed on the marketing
// site and 404'd in production).
describe("CommunityPage /pages/[slug]", () => {
  it("renders a markdown paste in-app", async () => {
    stubPaste({
      slug: "my-page-abc123",
      title: "My page",
      content_type: "markdown",
      content: "hello **world**",
      view_count: 3,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    render(await CommunityPage({ params: Promise.resolve({ slug: "my-page-abc123" }) }));
    expect(screen.getByRole("heading", { name: "My page" })).toBeInTheDocument();
    expect(screen.getByText("world")).toBeInTheDocument();
  });

  it("throws notFound for an unknown slug", async () => {
    stubPaste(null);
    await expect(
      CommunityPage({ params: Promise.resolve({ slug: "nope" }) }),
    ).rejects.toThrow();
  });
});
