import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { sweepAuth0SessionAndRedirectToLogin } from "../../managed/auth0/loggedOut";

// Sign-out bug regression: rolling responses from requests in flight during
// /auth/logout can re-set the session cookie the logout just deleted. The
// /logged-out landing must delete every session cookie variant again so the
// user actually ends up signed out.
describe("sweepAuth0SessionAndRedirectToLogin", () => {
  it("deletes all __session cookies (base + chunks) and redirects to /login", () => {
    const request = new NextRequest("https://app.example.com/logged-out", {
      headers: { cookie: "__session=a; __session__0=b; __session__1=c; other=keep" },
    });

    const response = sweepAuth0SessionAndRedirectToLogin(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://app.example.com/login");
    const setCookies = response.headers.getSetCookie();
    for (const name of ["__session", "__session__0", "__session__1"]) {
      expect(setCookies.some((c) => c.startsWith(`${name}=;`))).toBe(true);
    }
    expect(setCookies.some((c) => c.startsWith("other="))).toBe(false);
  });
});
