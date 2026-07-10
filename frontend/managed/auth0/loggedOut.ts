import { NextResponse, type NextRequest } from "next/server";

// Auth0 sends the browser here after /auth/logout (the URL must be listed in
// the Auth0 application's Allowed Logout URLs). The logout response already
// deleted the session cookie, but a request that was in flight at that moment
// can carry a response that re-sets it, resurrecting the session. Deleting the
// cookie again here — after the Auth0 round trip — closes that window.
export function sweepAuth0SessionAndRedirectToLogin(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/login", request.url));
  for (const cookie of request.cookies.getAll()) {
    // Covers the SDK's base cookie (__session) and its chunks (__session__0…).
    if (cookie.name.startsWith("__session")) {
      response.cookies.delete(cookie.name);
    }
  }
  return response;
}
