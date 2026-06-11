import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { subscribePageEvents } from "./pageEvents";

vi.mock("@/lib/api", () => ({
  API_BASE: "",
  getAuthToken: vi.fn(async () => "auth0-access-token"),
}));

describe("subscribePageEvents", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("authenticates each connection with the resolved auth token", async () => {
    vi.mocked(fetch).mockResolvedValue({ status: 401, ok: false } as Response);

    const unsubscribe = subscribePageEvents("ws-1", () => {});
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    unsubscribe();

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/pages/events",
      expect.objectContaining({
        headers: { Authorization: "Bearer auth0-access-token" },
      }),
    );
  });

  it("stops reconnecting on 401 instead of hammering the endpoint", async () => {
    vi.useFakeTimers();
    vi.mocked(fetch).mockResolvedValue({ status: 401, ok: false } as Response);

    const unsubscribe = subscribePageEvents("ws-1", () => {});
    await vi.advanceTimersByTimeAsync(10_000);

    expect(fetch).toHaveBeenCalledTimes(1);
    unsubscribe();
    vi.useRealTimers();
  });
});
