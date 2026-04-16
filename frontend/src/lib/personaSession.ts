import { getIronSession, type IronSession } from "iron-session";
import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

export interface PersonaSessionData {
  apiKey?: string;
}

function sessionOptions() {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 32) {
    throw new Error(
      "SESSION_SECRET must be set and at least 32 characters long."
    );
  }
  return {
    password: secret,
    cookieName: "boozle_persona",
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax" as const,
      path: "/",
      maxAge: 60 * 60 * 24 * 7, // 7 days
    },
  };
}

/** Read the persona session from the Next.js cookie store (Server Components / Route Handlers). */
export async function getPersonaSession(): Promise<IronSession<PersonaSessionData>> {
  const cookieStore = await cookies();
  return getIronSession<PersonaSessionData>(cookieStore, sessionOptions());
}

/**
 * Read the persona session from a raw NextRequest, usable inside the BFF proxy
 * where `cookies()` is not available.
 */
export async function getPersonaSessionFromRequest(
  req: NextRequest,
  res: NextResponse
): Promise<IronSession<PersonaSessionData>> {
  return getIronSession<PersonaSessionData>(req, res, sessionOptions());
}
