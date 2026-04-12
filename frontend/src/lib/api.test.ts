import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("apiFetch (BFF proxy)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("routes requests through /api/proxy/ instead of direct backend URL", async () => {
    const { register } = await import("./api");

    const mockResponse = {
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "1", name: "test", type: "human", api_key: "mc_key" }),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    await register("test", "human");

    expect(fetch).toHaveBeenCalledWith(
      "/api/proxy/users/register",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    );

    // The browser must NOT be sending an Authorization header — the BFF proxy
    // attaches it server-side from the session cookie.
    const callArgs = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const headers = callArgs?.headers as Record<string, string>;
    expect(headers?.["Authorization"]).toBeUndefined();
  });

  it("throws on non-ok response with detail from body", async () => {
    const { getMe } = await import("./api");

    const mockResponse = {
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ detail: "Invalid token" }),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    await expect(getMe()).rejects.toThrow("Invalid token");
  });

  it("handles 204 No Content responses", async () => {
    const { deleteWorkspace } = await import("./api");

    const mockResponse = {
      ok: true,
      status: 204,
      json: () => Promise.resolve(undefined),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    const result = await deleteWorkspace("ws-1");
    expect(result).toBeUndefined();
  });

  it("fetchWsToken returns null when /api/ws-token returns 401", async () => {
    const { fetchWsToken } = await import("./api");

    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ token: null }),
    } as Response);

    const token = await fetchWsToken();
    expect(token).toBeNull();
  });

  it("fetchWsToken returns the token from /api/ws-token", async () => {
    const { fetchWsToken } = await import("./api");

    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ token: "eyJhbGciOiJSUzI1NiJ9.stub" }),
    } as Response);

    const token = await fetchWsToken();
    expect(token).toBe("eyJhbGciOiJSUzI1NiJ9.stub");
  });
});
