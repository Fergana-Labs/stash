import { type NextRequest } from "next/server";
import { getAuth0Client } from "@/lib/auth0";

// Routes that require an active session. Any other path is publicly accessible.
const PROTECTED_ROUTES = [
  "/workspaces",
  "/rooms",
  "/notebooks",
  "/memory",
  "/tables",
  "/search",
];

function isProtectedRoute(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export async function proxy(request: NextRequest) {
  let auth0;
  try {
    auth0 = getAuth0Client();
  } catch {
    // Auth0 is not configured. If someone hits an /api/auth/* route directly,
    // return a clear error instead of letting it fall through to the backend proxy.
    if (request.nextUrl.pathname.startsWith("/api/auth/")) {
      return new Response(
        JSON.stringify({ error: "Auth0 is not configured on this server. Set AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, and AUTH0_SECRET in frontend/.env.local." }),
        { status: 501, headers: { "Content-Type": "application/json" } },
      );
    }
    // All other routes — pass through. Persona/API key auth still works.
    return;
  }

  // Auth0 SDK intercepts /api/auth/* (login, logout, callback, token, etc.)
  // and manages session cookies on all responses.
  let authResponse: Response;
  try {
    authResponse = await auth0.middleware(request);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("timeout") || msg.includes("TimeoutError") || msg.includes("aborted")) {
      return new Response(
        "Auth service temporarily unreachable. Please check your connection.",
        { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } },
      );
    }
    throw err;
  }

  // Let the SDK fully handle its own routes
  if (request.nextUrl.pathname.startsWith("/api/auth/")) {
    return authResponse;
  }

  // Redirect unauthenticated users away from protected routes
  if (isProtectedRoute(request.nextUrl.pathname)) {
    const session = await auth0.getSession(request);
    if (!session) {
      const loginUrl = new URL("/api/auth/login", request.url);
      loginUrl.searchParams.set("returnTo", request.nextUrl.pathname);
      return Response.redirect(loginUrl);
    }
  }

  return authResponse;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
