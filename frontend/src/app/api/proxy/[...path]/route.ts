import { type NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getAuth0Client } from "@/lib/auth0";
import { getIronSession } from "iron-session";
import { type PersonaSessionData } from "@/lib/personaSession";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

// Headers that must never be forwarded to the backend
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
]);

function ironOptions() {
  const secret = process.env.SESSION_SECRET ?? "";
  return {
    password: secret.length >= 32 ? secret : secret.padEnd(32, "0"),
    cookieName: "boozle_persona",
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax" as const,
      path: "/",
    },
  };
}

async function resolveToken(): Promise<string | null> {
  // 1. Auth0 session (human accounts)
  try {
    const auth0 = getAuth0Client();
    const session = await auth0.getSession();
    if (session?.tokenSet?.accessToken) return session.tokenSet.accessToken;
  } catch {
    // Auth0 not configured or no active session
  }

  // 2. Persona session (machine accounts — httpOnly encrypted cookie)
  try {
    const cookieStore = await cookies();
    const session = await getIronSession<PersonaSessionData>(
      cookieStore,
      ironOptions()
    );
    if (session.apiKey) return session.apiKey;
  } catch {
    // SESSION_SECRET not set or cookie invalid
  }

  return null;
}

async function handler(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await context.params;
  const token = await resolveToken();

  // Build the upstream URL
  const upstream = new URL(`/api/v1/${path.join("/")}`, BACKEND);
  upstream.search = request.nextUrl.search;

  // Build forwarded headers
  const forwardHeaders = new Headers();
  for (const [key, value] of request.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      forwardHeaders.set(key, value);
    }
  }
  if (token) {
    forwardHeaders.set("Authorization", `Bearer ${token}`);
  }
  // Ensure the backend knows the real origin
  forwardHeaders.set("X-Forwarded-Host", request.headers.get("host") ?? "");

  const method = request.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";

  const upstreamRes = await fetch(upstream.toString(), {
    method,
    headers: forwardHeaders,
    ...(hasBody
      ? {
          body: request.body,
          duplex: "half",
        }
      : {}),
  });

  // Strip hop-by-hop from response headers
  const resHeaders = new Headers();
  for (const [key, value] of upstreamRes.headers.entries()) {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      resHeaders.set(key, value);
    }
  }

  return new NextResponse(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: resHeaders,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
