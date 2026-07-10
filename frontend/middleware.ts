import { NextResponse, type NextRequest } from "next/server";

import { sweepAuth0SessionAndRedirectToLogin } from "@managed/auth0/loggedOut";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export async function middleware(request: NextRequest) {
  if (!AUTH0_ENABLED) return NextResponse.next();
  if (request.nextUrl.pathname === "/logged-out") {
    return sweepAuth0SessionAndRedirectToLogin(request);
  }
  const { runAuth0Middleware } = await import("@managed/auth0/middleware");
  return runAuth0Middleware(request);
}

export const config = {
  matcher: [
    // Run on all routes except Next.js internals, static assets, our own API,
    // and public Product Stash routes which render without authentication.
    "/((?!_next/static|_next/image|favicon.ico|icon.svg|api/v1/|design/|discover|stashes/).*)",
  ],
};
