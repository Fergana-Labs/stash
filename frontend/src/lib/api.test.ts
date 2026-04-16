import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { setToken, clearToken } from "./api";

describe("token management", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("setToken stores token in localStorage", () => {
    setToken("test-token-123");
    expect(localStorage.getItem("stash_token")).toBe("test-token-123");
  });

  it("clearToken removes token from localStorage", () => {
    localStorage.setItem("stash_token", "test-token-123");
    clearToken();
    expect(localStorage.getItem("stash_token")).toBeNull();
  });
});

describe("apiFetch", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("includes Authorization header when token is set", async () => {
    const { register } = await import("./api");
    localStorage.setItem("stash_token", "my-token");

    const mockResponse = {
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "1", name: "test", type: "human", api_key: "key" }),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    await register("test", "human");

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/users/register",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer my-token",
        }),
      })
    );
  });

  it("throws on non-ok response with detail from body", async () => {
    const { getMe } = await import("./api");
    localStorage.setItem("stash_token", "my-token");

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
    localStorage.setItem("stash_token", "my-token");

    const mockResponse = {
      ok: true,
      status: 204,
      json: () => Promise.resolve(undefined),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    const result = await deleteWorkspace("ws-1");
    expect(result).toBeUndefined();
  });
});
