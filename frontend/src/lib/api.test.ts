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
    const { deleteSource } = await import("./api");
    localStorage.setItem("stash_token", "my-token");

    const mockResponse = {
      ok: true,
      status: 204,
      json: () => Promise.resolve(undefined),
    };
    vi.mocked(fetch).mockResolvedValue(mockResponse as Response);

    const result = await deleteSource("src-1");
    expect(result).toBeUndefined();
  });
});

describe("managed Auth0 token handling", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_AUTH0_ENABLED", "true");
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("ignores stored API keys and uses the Auth0 access token", async () => {
    const { getMe, getToken, setToken } = await import("./api");
    localStorage.setItem("stash_token", "legacy-api-key");
    setToken("new-api-key");

    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ token: "auth0-access-token" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            id: "1",
            name: "sam",
            display_name: "Sam",
            description: "",
            created_at: "2026-01-01T00:00:00Z",
            last_seen: "2026-01-01T00:00:00Z",
          }),
      } as Response);

    await getMe();

    expect(getToken()).toBeNull();
    expect(fetch).toHaveBeenNthCalledWith(1, "/auth/access-token", {
      credentials: "include",
    });
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/v1/users/me",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer auth0-access-token",
        }),
      }),
    );
  });

  it("caches the Auth0 access token so API calls don't double up requests", async () => {
    const { getAuthToken } = await import("./api");

    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ token: "auth0-access-token" }),
    } as Response);

    expect(await getAuthToken()).toBe("auth0-access-token");
    expect(await getAuthToken()).toBe("auth0-access-token");

    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("revokeStoredApiKey revokes the legacy browser key server-side, not just locally", async () => {
    const { revokeStoredApiKey } = await import("./api");
    localStorage.setItem("stash_token", "legacy-api-key");

    vi.mocked(fetch).mockResolvedValue({ ok: true } as Response);

    await revokeStoredApiKey();

    expect(localStorage.getItem("stash_token")).toBeNull();
    expect(fetch).toHaveBeenCalledWith("/api/v1/users/logout", {
      method: "POST",
      headers: { Authorization: "Bearer legacy-api-key" },
    });
  });

  it("getAgentApiKey never mints a key under managed Auth0 — browser key minting is disabled", async () => {
    const { getAgentApiKey } = await import("./api");

    expect(getAgentApiKey()).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("self-hosted agent key", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it("getAgentApiKey returns the stored browser key", async () => {
    const { getAgentApiKey, setToken } = await import("./api");
    setToken("self-hosted-key");

    expect(getAgentApiKey()).toBe("self-hosted-key");
  });
});

// Every scoped read and write carries the selected workspace's scope_user_id;
// the backend reads it to serve the org knowledge base instead of the personal
// one. Personal scope must send no header at all — an empty/absent header is
// what keeps today's behavior the default.
describe("workspace scope header", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function okResponse() {
    return { ok: true, status: 200, json: () => Promise.resolve({}) } as Response;
  }

  it("apiFetch sends X-Stash-Scope when a workspace scope is selected", async () => {
    const { listMyWorkspaces } = await import("./api");
    const { setScope } = await import("./scope-store");
    vi.mocked(fetch).mockResolvedValue(okResponse());

    setScope({ scope_user_id: "ws-scope-user", name: "Acme" });
    await listMyWorkspaces();

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/me/workspaces",
      expect.objectContaining({
        headers: expect.objectContaining({ "X-Stash-Scope": "ws-scope-user" }),
      }),
    );
  });

  it("apiFetch omits X-Stash-Scope in personal scope", async () => {
    const { listMyWorkspaces } = await import("./api");
    const { setScope } = await import("./scope-store");
    vi.mocked(fetch).mockResolvedValue(okResponse());

    setScope(null);
    await listMyWorkspaces();

    const headers = vi.mocked(fetch).mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers["X-Stash-Scope"]).toBeUndefined();
  });

  it("fetchAuthed sends X-Stash-Scope when a workspace scope is selected", async () => {
    const { fetchAuthed } = await import("./api");
    const { setScope } = await import("./scope-store");
    vi.mocked(fetch).mockResolvedValue(okResponse());

    setScope({ scope_user_id: "ws-scope-user", name: "Acme" });
    await fetchAuthed("/api/v1/me/files");

    expect(fetch).toHaveBeenCalledWith("/api/v1/me/files", {
      headers: expect.objectContaining({ "X-Stash-Scope": "ws-scope-user" }),
    });
  });
});
