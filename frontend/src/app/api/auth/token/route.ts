import { type NextRequest } from "next/server";
import { getAuth0Client } from "@/lib/auth0";

/**
 * GET /api/auth/token
 *
 * Returns the current Auth0 access token from the server-side session.
 * Called by AuthTokenBridge / fetchAccessToken() to keep the in-memory
 * API client token in sync with the Auth0 session cookie.
 */
export async function GET(_request: NextRequest) {
  try {
    const auth0 = getAuth0Client();
    const session = await auth0.getSession();
    if (!session?.tokenSet?.accessToken) {
      return Response.json({ token: null }, { status: 401 });
    }
    return Response.json({ token: session.tokenSet.accessToken });
  } catch {
    return Response.json({ token: null }, { status: 401 });
  }
}
