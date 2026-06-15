import { NextResponse, type NextRequest } from "next/server";

import { ADMIN_COOKIE_NAME, verifySession } from "@/lib/admin-auth";

const AUTH0_ENABLED = process.env.NEXT_PUBLIC_AUTH0_ENABLED === "true";

// Next.js 16 renamed `middleware` → `proxy`; the export must also be named
// `proxy` for the convention to apply.
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Agent API for /pages: a page.tsx and route.ts can't share a segment,
  // so writes rewrite to /api/pages route handlers.
  //   curl -X POST joinstash.ai/pages -d '# Hello'
  //   curl -X PATCH  "joinstash.ai/pages/{slug}?token=…" -d '…'
  //   curl -X DELETE "joinstash.ai/pages/{slug}?token=…"
  // (Server-action POSTs to /pages carry a Next-Action header — those
  // belong to the composer UI, not the agent API.)
  if (pathname === "/pages" && request.method === "POST" && !request.headers.get("next-action")) {
    return NextResponse.rewrite(new URL("/api/pages", request.url));
  }
  // Comments on the canonical domain (no Next pages live at these paths):
  //   GET/POST   joinstash.ai/pages/{slug}/comments
  //   PATCH/DEL  joinstash.ai/pages/{slug}/comments/{id}?token=…
  if (/^\/pages\/[^/]+\/comments(\/[^/]+)?$/.test(pathname)) {
    return NextResponse.rewrite(
      new URL(`/api${pathname}${request.nextUrl.search}`, request.url),
    );
  }
  const pasteSlug = pathname.match(/^\/pages\/([^/]+)$/)?.[1];
  if (pasteSlug && (request.method === "PATCH" || request.method === "DELETE")) {
    return NextResponse.rewrite(new URL(`/api/pages/${pasteSlug}${request.nextUrl.search}`, request.url));
  }
  // Content negotiation on the canonical URL: curl/agents (Accept without
  // text/html) get the raw source; browsers get the rendered page. The
  // RSC-header guard keeps Next's client-navigation fetches on the page.
  if (pasteSlug && request.method === "GET") {
    const accept = request.headers.get("accept") ?? "";
    if (!accept.includes("text/html") && !request.headers.get("rsc")) {
      return NextResponse.rewrite(new URL(`/pages/${pasteSlug}/raw`, request.url));
    }
  }

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
