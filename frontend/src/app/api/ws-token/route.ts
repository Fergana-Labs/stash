import { cookies } from "next/headers";
import { getIronSession } from "iron-session";
import { getAuth0Client } from "@/lib/auth0";
import { type PersonaSessionData } from "@/lib/personaSession";

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

/**
 * GET /api/ws-token
 *
 * Returns a short-lived credential for opening a WebSocket connection.
 * The token is sourced from the server-side session — the browser never
 * needs to store it in localStorage; it is fetched right before each
 * WebSocket connection is established and used immediately.
 */
export async function GET() {
  // 1. Auth0 session (human accounts)
  try {
    const auth0 = getAuth0Client();
    const session = await auth0.getSession();
    if (session?.tokenSet?.accessToken) {
      return Response.json({ token: session.tokenSet.accessToken });
    }
  } catch {
    // Auth0 not configured or no active session
  }

  // 2. Persona session (machine accounts)
  try {
    const cookieStore = await cookies();
    const session = await getIronSession<PersonaSessionData>(
      cookieStore,
      ironOptions()
    );
    if (session.apiKey) {
      return Response.json({ token: session.apiKey });
    }
  } catch {
    // SESSION_SECRET not set or cookie corrupted
  }

  return Response.json({ token: null }, { status: 401 });
}
