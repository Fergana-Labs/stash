import { describe, expect, it, beforeEach } from "vitest";
import { consumeManualAuth0Logout, markManualAuth0Logout } from "./authLogout";

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
