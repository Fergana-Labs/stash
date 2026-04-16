import { NextResponse, type NextRequest } from "next/server";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

export async function middleware(request: NextRequest) {
  if (!AUTH0_ENABLED) return NextResponse.next();
  const { runAuth0Middleware } = await import("@managed/auth0/middleware");
  return runAuth0Middleware(request);
}

export const config = {
  matcher: [
    // Run on all routes except Next.js internals, static assets, and our own API.
    "/((?!_next/static|_next/image|favicon.ico|icon.svg|api/v1/).*)",
  ],
};
