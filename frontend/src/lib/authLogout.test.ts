import { describe, expect, it, beforeEach } from "vitest";
import { auth0LogoutUrl, consumeManualAuth0Logout, markManualAuth0Logout } from "./authLogout";

describe("Auth0 manual logout marker", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("is consumed once after manual logout", () => {
    markManualAuth0Logout();

    expect(consumeManualAuth0Logout()).toBe(true);
    expect(consumeManualAuth0Logout()).toBe(false);
  });
});

describe("auth0LogoutUrl", () => {
  // Logout must land on /logged-out (an Allowed Logout URL) so the middleware
  // can sweep session cookies resurrected by requests in flight mid-logout.
  it("sends Auth0 back to this origin's /logged-out sweep route", () => {
    expect(auth0LogoutUrl()).toBe(
      `/auth/logout?returnTo=${encodeURIComponent(`${window.location.origin}/logged-out`)}`,
    );
  });
});
