import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Telemetry must flow on managed Auth0 deployments too, where there is no
// localStorage API key — flush has to resolve the token via getAuthToken.
vi.mock("./api", () => ({
  getAuthToken: vi.fn(async () => "auth0-access-token"),
}));

describe("analytics flush", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true } as Response));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("sends batched events with the resolved auth token", async () => {
    const { track } = await import("./analytics");

    track("onboarding.viewed", { has_path: false });
    await vi.advanceTimersByTimeAsync(1000);

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/analytics/events",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer auth0-access-token",
        }),
      }),
    );
  });
});
