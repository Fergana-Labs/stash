import { describe, it, expect, beforeEach, vi } from "vitest";

// The selected scope survives reloads (it is what every request is stamped
// with), so persistence is the behavior worth pinning down: a workspace round
// trips through localStorage, and clearing it returns the user to personal —
// never to a stale workspace.
describe("scope-store", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it("defaults to personal scope when nothing is stored", async () => {
    const { getScope, getScopeUserId } = await import("./scope-store");

    expect(getScope()).toBeNull();
    expect(getScopeUserId()).toBeNull();
  });

  it("persists the selected workspace under stash_scope", async () => {
    const { setScope } = await import("./scope-store");

    setScope({ scope_user_id: "ws-scope-user", name: "Acme" });

    expect(JSON.parse(localStorage.getItem("stash_scope")!)).toEqual({
      scope_user_id: "ws-scope-user",
      name: "Acme",
    });
  });

  it("restores a stored workspace on load", async () => {
    localStorage.setItem(
      "stash_scope",
      JSON.stringify({ scope_user_id: "ws-scope-user", name: "Acme" }),
    );
    const { getScope, getScopeUserId } = await import("./scope-store");

    expect(getScope()).toEqual({ scope_user_id: "ws-scope-user", name: "Acme" });
    expect(getScopeUserId()).toBe("ws-scope-user");
  });

  it("clears back to personal scope", async () => {
    const { setScope, getScopeUserId } = await import("./scope-store");
    setScope({ scope_user_id: "ws-scope-user", name: "Acme" });

    setScope(null);

    expect(getScopeUserId()).toBeNull();
    expect(localStorage.getItem("stash_scope")).toBeNull();
  });
});
