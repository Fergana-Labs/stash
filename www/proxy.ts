import { NextResponse, type NextRequest } from "next/server";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Next.js 16 renamed `middleware` → `proxy`; the export must also be named
// `proxy` for the convention to apply.
export async function proxy(request: NextRequest) {
  if (!AUTH0_ENABLED) return NextResponse.next();
  const { runAuth0Middleware } = await import("@managed/auth0/middleware");
  return runAuth0Middleware(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)",
  ],
};
