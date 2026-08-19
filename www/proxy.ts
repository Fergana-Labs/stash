import { NextResponse, type NextRequest } from "next/server";

import { ADMIN_COOKIE_NAME, verifySession } from "@/lib/admin-auth";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Next.js 16 renamed `middleware` → `proxy`; the export must also be named
// `proxy` for the convention to apply.
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/admin") && pathname !== "/admin/login") {
    const session = request.cookies.get(ADMIN_COOKIE_NAME)?.value;
    const ok = await verifySession(session);
    if (!ok) {
      return NextResponse.redirect(new URL("/admin/login", request.url));
    }
  }

  if (!AUTH0_ENABLED) return NextResponse.next();
  const { runAuth0Middleware } = await import("@managed/auth0/middleware");
  return runAuth0Middleware(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)",
  ],
};
